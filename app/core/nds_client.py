import os
import re
import stat
import struct
import aioftp
import asyncio
import inspect
import asyncssh
from io import BytesIO
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from app.core.logger import log


# ZIP 文件格式常量
ZIP_MAGIC = b"PK\003\004"      # 本地文件头签名 (Local file header signature)
ZIP64_MAGIC = b"PK\x06\x06"    # ZIP64结束中央目录记录签名 (ZIP64 end of central directory signature)
ZIP64_LOCATOR = b"PK\x06\x07"  # ZIP64结束中央目录定位器签名 (ZIP64 end of central directory locator signature)
ZIP_DIR_MAGIC = b"PK\001\002"   # 中央目录文件头签名 (Central directory file header signature)
ZIP_END_MAGIC = b"PK\005\006"   # 结束中央目录记录签名 (End of central directory signature)

# ZIP文件头结构格式
ZIP_LOCAL_HEADER = "<4s2B4HL2L2H"  # 本地文件头格式: 签名(4s) + 版本(2B) + 标志位等(4H) + 压缩信息(2L) + 文件信息(2H)
ZIP_CENTRAL_DIR = "<4s4B4HL2L5H2L"  # 中央目录结构: 签名(4s) + 版本等(4B) + 标志位(4H) + 压缩信息(2L) + 文件信息(5H) + 偏移量等(2L)
ZIP_END_RECORD = "<4s4H2LH"  # 目录结束记录: 签名(4s) + 磁盘信息(4H) + 目录信息(2L) + 注释长度(H)
ZIP64_END_RECORD = "<4sQ2H2L4Q"  # ZIP64目录结束记录: 签名(4s) + 记录大小(Q) + 版本(2H) + 磁盘信息(2L) + 目录信息(4Q)
ZIP64_LOCATOR_RECORD = "<4sLQL"  # ZIP64定位器: 签名(4s) + 磁盘号(L) + 相对偏移(Q) + 磁盘总数(L)


class KeyType(dict):
    def __getattr__(self, item):
        if item not in self:
            return None
        return self[item]

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, item):
        if item in self:
            del self[item]


def is_regex(pattern):
    # 检查正则表达式合法性
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


class NDSError(Exception):
    """NDS客户端异常基类"""

    def __init__(self, message: str, from_module: Optional[str] = None, level: int = 0, nds_id: Optional[int] = None):
        super().__init__(message)
        caller_frame = inspect.currentframe().f_back
        self.message = message
        self.from_module = from_module or caller_frame.f_globals["__name__"]
        self.function = "" if from_module else f".{caller_frame.f_code.co_name}"
        self.level = level
        self.nds_id = nds_id
        
        # 修改日志消息格式，添加nds_id信息
        nds_info = f"[NDS_ID:{self.nds_id}] " if self.nds_id is not None else ""
        log.error(f"{nds_info}{self.__str__()}")

    def __str__(self):
        nds_info = f" NDS_ID[{self.nds_id}]" if self.nds_id is not None else ""
        return f"ErrLevel({self.level}) From[{self.from_module}{self.function}]{nds_info} Error: {self.message}"


class NDSConnectError(NDSError):
    """连接相关异常"""
    pass


class NDSFileNotFoundError(NDSError):
    """文件不存在异常"""
    pass


class NDSZipError(NDSError):
    """ZIP文件解析异常"""
    pass


class NDSIOError(NDSError):
    """IO操作异常"""
    pass


# noinspection PyBroadException
class NDSClient:
    """NDS文件传输客户端

    支持FTP和SFTP协议的文件传输和ZIP文件解析
    """

    SUPPORTED_PROTOCOLS = {"FTP", "SFTP"}
    RETRY_COUNT = 3
    RETRY_DELAY = 1  # 秒

    def __init__(self, protocol: str, host: str, port: int, user: str, passwd: str,
                 pool_num: Optional[int] = None, nds_id: Optional[str] = None):
        if protocol not in self.SUPPORTED_PROTOCOLS:
            raise NDSError(f"Unsupported protocol: {protocol}", level=1, nds_id=nds_id)

        self.protocol = protocol
        self.host = host
        self.port = port
        self.user = user
        self.passwd = passwd
        self.pool_num = pool_num
        self.ID = int(nds_id) if nds_id is not None else None

        # 私有属性
        self.__ftp = None
        self.__sftp = None
        self.client = None
        self.__stream = None
        self.stream_path = None
        self.stream_info: Dict[str, Any] = {}
        self.__stream_offset = 0

        # 锁对象
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def connection(self):
        """异步上下文管理器用于自动连接和关闭"""
        try:
            await self.connect()
            yield self
        finally:
            await self.close_connect()

    async def connect(self, retry_count: int = None):
        """建立连接"""
        retry = self.RETRY_COUNT if not retry_count else retry_count
        for attempt in range(retry):
            try:
                if self.protocol == "FTP":
                    self.__ftp = aioftp.Client()
                    await self.__ftp.connect(self.host, self.port)
                    await self.__ftp.login(self.user, self.passwd)
                    self.client = self.__ftp
                else:  # SFTP
                    self.__sftp = await asyncssh.connect(
                        host=self.host,
                        port=self.port,
                        username=self.user,
                        password=self.passwd,
                        known_hosts=None
                    )
                    self.client = await self.__sftp.start_sftp_client()
                return True
            except Exception as e:
                if attempt == self.RETRY_COUNT - 1:
                    raise NDSConnectError(f"Connect error after {retry} attempts: {str(e)}", level=1, nds_id=self.ID)
                await asyncio.sleep(self.RETRY_DELAY)

    async def check_connect(self) -> bool:
        """检查连接状态"""
        try:
            if not self.client:
                return False

            if self.protocol == "FTP":
                log.debug(f"[NDS_ID:{self.ID}] Checking FTP connection")
                try:
                    await self.client.change_directory("/")
                    return True
                except aioftp.StatusCodeError as e:
                    # 有些FTP服务器可能返回不同的成功状态码
                    return e.received_codes[0] in {'200', '250', '212', '226', '257'}
                except Exception:
                    return False
            else:  # SFTP
                if not self.__sftp:
                    log.debug(f"[NDS_ID:{self.ID}] No SFTP connection")
                    return False
                # 定义检查函数列表
                checks = [
                    lambda: self.client.realpath('.'),
                    lambda: self.client.realpath('/'),
                    lambda: self.client.stat('/'),
                    lambda: self.client.stat('.'),
                    lambda: self.client.lstat("."),
                    lambda: self.client.listdir('/')
                ]
                # 尝试执行每个检查，任意一个成功就返回 True
                for check in checks:
                    try:
                        await check()
                        return True
                    except Exception:
                        continue
                # 所有检查都失败返回 False
                return False
        except Exception as e:
            log.warning(f"[NDS_ID:{self.ID}] Connection check failed: {str(e)}")
            return False

    async def close_connect(self):
        """关闭连接"""
        try:
            if self.protocol == "FTP" and self.__ftp:
                try:
                    await self.__ftp.quit()
                except Exception as e:
                    log.warning(f"[NDS_ID:{self.ID}] Error closing FTP connection: {e}")
            elif self.protocol == "SFTP" and self.__sftp:
                try:
                    self.__sftp.close()
                except Exception as e:
                    log.warning(f"[NDS_ID:{self.ID}] Error closing SFTP connection: {e}")
        except Exception as e:
            log.warning(f"[NDS_ID:{self.ID}] Error in close_connect: {e}")
        finally:
            # 确保所有引用都被清理
            self.client = None
            self.__ftp = None
            self.__sftp = None

    async def scan(self, scan_path: str, filter_pattern: Optional[str] = None) -> List[str]:
        """扫描远程目录并返回文件列表"""
        if not scan_path:
            raise NDSError("Invalid scan path", level=1)

        files = []
        use_filter = True if filter_pattern and is_regex(filter_pattern) else False
        if filter_pattern and not use_filter:
            raise NDSError("Scanner filter error", level=1)

        if self.client is None:
            raise NDSError("Not init NDS Client", "NDSClient.scan", -1)

        if self.protocol == "FTP":

            try:
                async for path, info in self.client.list(scan_path, recursive=True):
                    if info.get('type') == 'file':
                        if use_filter:
                            if re.search(filter_pattern, str(path)):
                                files.append(str(path))
                        else:
                            files.append(str(path))
            except Exception as e:
                await self.close_connect()
                raise e

        elif self.protocol == "SFTP":
            #  使用队列方式代替函数递归
            stack = [scan_path]
            while stack:
                current_path = stack.pop()
                async for entry in self.client.scandir(current_path):
                    full_path = f"{current_path.rstrip('/')}/{entry.filename}"
                    if stat.S_ISDIR(entry.attrs.permissions):
                        stack.append(full_path)
                    else:
                        if use_filter:
                            if re.search(filter_pattern, str(full_path)):
                                files.append(str(full_path))
                        else:
                            files.append(str(full_path))
        else:
            raise NDSError("Invalid protocol, only support FTP and SFTP", "NDSClient.scan", 1)
        return files

    async def file_exists(self, remote_path: str) -> bool:
        """检查远程文件是否存在"""
        try:
            await self.client.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            raise NDSError(str(e), f"NDSClient.file_exists remote_path:{remote_path}", 1, self.ID)

    async def stat(self, file_path: str) -> Optional[Dict[str, Any]]:
        """获取文件状态信息"""
        try:
            if not await self.file_exists(file_path):
                return None
            info_obj = await self.client.stat(file_path)
            if not info_obj:
                return None

            if self.protocol == "FTP":
                info = info_obj
                modify = info.get('modify')
                modify = datetime(
                    int(modify[:4]), int(modify[4:6]), int(modify[6:8]),
                    int(modify[8:10]), int(modify[10:12]), int(modify[12:14]), 0
                ).strftime('%Y-%m-%d %H:%M:%S') if modify else modify
            elif self.protocol == "SFTP":
                info = {attr: getattr(info_obj, attr, None) for attr in dir(info_obj) if not attr.startswith('_')}
                modify = info.get('modify')
                modify = datetime.fromtimestamp(modify).strftime('%Y-%m-%d %H:%M:%S') if modify else modify
            else:
                return None

            self.stream_info = {
                "file_path": file_path,
                "directory": file_path.rsplit('/', 1)[0],
                "filename": file_path.rsplit('/', 1)[1],
                "size": int(info.get('size')),
                "modify": modify
            }
            return self.stream_info
        except Exception:
            return None

    async def close(self):
        """关闭打开的文件"""
        try:
            if self.__stream:
                # 先判断是否有close方法，且是协程函数
                if asyncio.iscoroutinefunction(self.__stream.close):
                    await self.__stream.close()
                self.__stream = None
        except Exception as e:
            log.error(f"[NDS_ID:{self.ID}] Error in close: {e}")

    async def open(self, file_path):
        self.stream_info = await self.stat(file_path)
        if not self.stream_info:
            raise NDSFileNotFoundError(f"File not found: {file_path}", nds_id=self.ID)
        if self.protocol == "SFTP":
            self.__stream = await self.client.open(file_path, 'rb')
        self.stream_path = file_path

    async def seek(self, offset: int = 0, whence: int = 0) -> None:
        """设置文件指针位置

        Args:
            offset: 偏移量
            whence: 起始位置(0:开始, 1:当前, 2:结尾)

        Raises:
            ValueError: 参数无效
        """
        if whence not in (0, 1, 2):
            raise ValueError("whence must be 0, 1 or 2")

        async with self._lock:
            self.__stream_offset = (
                self.stream_info['size'] - abs(offset) if whence == 2
                else self.__stream_offset + offset if whence == 1
                else offset
            )

    async def read(self, size: Optional[int] = None, offset: Optional[int] = None) -> bytes:
        """读取文件内容

        Args:
            size: 要读取的字节数, None表示读取到文件末尾
            offset: 偏移量(0:开始, 1:当前, 2:结尾), None表示不设置偏移量, 可配合seek使用
        Returns:
            读取的字节数据
        Raises:
            NDSIOError: 读取过程中发生错误
        """
        if self.client is None:
            raise NDSError("Not init NDS Client", "NDSClient.read", -1, self.ID)
        if self.stream_path is None:
            raise NDSError("File is not open", "NDSClient.read", 0, self.ID)
        if offset is not None:
            await self.seek(offset)

        async with self._lock:
            if self.protocol == "FTP":
                try:
                    stream = await self.client.get_stream(
                        "RETR " + self.stream_path,
                        ('1xx', '200', '250'),  # 接受更多有效的FTP响应码
                        offset=self.__stream_offset
                    )
                    tmp_io = BytesIO()
                    size = size if size and self.__stream_offset + size <= self.stream_info['size'] else \
                        self.stream_info['size'] - self.__stream_offset
                    total = size
                    offset = self.__stream_offset
                    while total > 0:
                        block = await stream.read(min(abs(total), 2048))
                        if not block:
                            break
                        tmp_io.write(block)
                        total -= len(block)
                        offset += len(block)
                        if size and tmp_io.tell() >= size:
                            await stream.finish('xxx')
                            break
                    self.__stream_offset = self.__stream_offset + size if size else self.stream_info["size"]
                    return tmp_io.getvalue()[0:size]
                except Exception as e:
                    raise NDSError(f'read warning: {e}', "NDSClient.read", -1, self.ID)
            elif self.protocol == "SFTP":
                if self.__stream is None:
                    raise NDSError("File is not open", "NDSClient.read", 1, self.ID)
                try:
                    size = size if size and self.__stream_offset + size <= self.stream_info['size'] else \
                        self.stream_info['size'] - self.__stream_offset
                    data = await self.__stream.read(size, self.__stream_offset)
                    self.__stream_offset = self.__stream_offset + size if size else self.stream_info['size']
                except Exception as e:
                    raise NDSError(f'read warning: {e}', "NDSClient.read", -1, self.ID)
                return data
            else:
                raise NDSError("Invalid protocol, only support FTP and SFTP", "NDSClient.read", 1, self.ID)

    async def get_zip_info(self, file_path: str = None) -> list[KeyType[Any, Any]]:
        """解析ZIP文件结构并返回文件信息列表

        Args:
            file_path: 文件路径, 为None时使用当前打开的文件
        Returns:
            文件信息列表
        Raises:
            NDSZipError: 解析ZIP文件结构过程中发生错误
        """
        if file_path:
            await self.open(file_path)
        # 读取文件头
        header_size = struct.calcsize(ZIP_LOCAL_HEADER)
        await self.seek(0, 0)
        tmp_data = await self.read(header_size)
        header_data = struct.unpack(ZIP_LOCAL_HEADER, tmp_data)
        if len(tmp_data) != header_size or header_data[0] != ZIP_MAGIC:
            raise Exception("ZIP header warning")
        self.stream_info['header_size'] = header_data[10] + header_data[11] + header_size
        # 解析中央目录结构
        cd_end_size = struct.calcsize(ZIP_END_RECORD)  # sizeEndCentDir
        await self.seek(cd_end_size, 2)
        tmp_data = await self.read()
        if len(tmp_data) != cd_end_size or tmp_data[0:4] != ZIP_END_MAGIC or tmp_data[-2:] != b"\000\000":
            raise Exception("ZIP CentDirectory warning")  # 要么不是ZIP文件，要么带了注释，暂时不解决注释问题
        cd_rec = struct.unpack(ZIP_END_RECORD, tmp_data)
        cd_rec = list(cd_rec)
        cd_rec.append(b"")
        cd_rec.append(self.stream_info['size'] - cd_end_size)
        # 尝试读取ZIP64中央目录文件(用于兼容ZIP64)
        cd_end_64_size = struct.calcsize(ZIP64_END_RECORD)  # sizeEndCentDir64
        cd_end_l64_size = struct.calcsize(ZIP64_LOCATOR_RECORD)  # sizeEndCentDir64Locator
        if cd_end_size + cd_end_l64_size < self.stream_info['size']:
            await self.seek(-cd_end_size - cd_end_l64_size, 2)
            tmp_data = await self.read(cd_end_l64_size)
            if len(tmp_data) == cd_end_l64_size:
                sig, disk_no, _rel_off, disks = struct.unpack(ZIP64_LOCATOR_RECORD, tmp_data)
                if sig == ZIP64_LOCATOR:
                    if disk_no != 0 or disks > 1:
                        raise Exception("ZIP Files that span multiple disks are not supported")
                    # Assume no 'zip64 extensible data'
                    await self.seek(-cd_end_64_size - cd_end_l64_size - cd_end_64_size, 2)
                    tmp_data = await self.read(cd_end_64_size)
                    if len(tmp_data) == cd_end_64_size:
                        sig, _sz, _create_version, _read_version, disk_num, disk_dir, \
                            dir_count, dir_count2, dir_size, dir_offset = \
                            struct.unpack(ZIP64_END_RECORD, tmp_data)
                        if sig == ZIP64_MAGIC:
                            # 更新为ZIP64中央目录结构
                            cd_rec[0] = sig  # _ECD_SIGNATURE
                            cd_rec[1] = disk_num  # _ECD_DISK_NUMBER
                            cd_rec[2] = disk_dir  # _ECD_DISK_START
                            cd_rec[3] = dir_count  # _ECD_ENTRIES_THIS_DISK
                            cd_rec[4] = dir_count2  # _ECD_ENTRIES_TOTAL
                            cd_rec[5] = dir_size  # _ECD_SIZE
                            cd_rec[6] = dir_offset  # _ECD_OFFSET
        cd_end_size = cd_rec[5]  # _ECD_SIZE 中央目录字节尺寸
        cd_offset = cd_rec[6]  # _ECD_OFFSET 中央目录开始位置
        concat = cd_rec[9] - cd_end_size - cd_offset  # _ECD_LOCATION = 9
        concat -= (cd_end_64_size + cd_end_l64_size) if cd_rec[0] == ZIP64_MAGIC else 0  # ZIP64扩展结构
        offset = cd_offset + concat
        await self.seek(offset, 0)
        tmp_data = await self.read(cd_end_size)
        await self.close()
        data = BytesIO(tmp_data)
        cd_dir_size = struct.calcsize(ZIP_CENTRAL_DIR)  # sizeCentralDir
        total = 0
        file_info_array = []
        while total < cd_end_size:
            centdir = data.read(cd_dir_size)
            if len(centdir) != cd_dir_size:
                raise Exception("Truncated central directory")
            centdir = struct.unpack(ZIP_CENTRAL_DIR, centdir)
            if centdir[0] != ZIP_DIR_MAGIC:  # _CD_SIGNATURE = 0
                raise Exception("Bad magic number for central directory")
            if centdir[3] > 63:  # centdir[3]: extract_version, MAX_EXTRACT_VERSION = 63, 目前支持6.3及以下版本的ZIP包
                raise Exception("zip file version %.1f" % (centdir[3] / 10))

            info = KeyType()
            info.directory, info.file_name = os.path.split(self.stream_path)
            info.sub_file_name = data.read(centdir[12])  # _CD_FILENAME_LENGTH = 12
            flags = centdir[5]  # _CD_FLAG_BITS = 5
            # _MASK_UTF_FILENAME = 1 << 11 = 2048
            info.sub_file_name = info.sub_file_name.decode('utf-8') if flags & 2048 else info.sub_file_name.decode(
                'cp437')
            # _CD_LOCAL_HEADER_OFFSET 文件开始位置，需要加上文件头尺寸
            info.file_path = self.stream_info['file_path']
            info.header_offset = centdir[18] + self.stream_info['header_size']
            info.compress_size = centdir[10]
            info.file_size = centdir[11]
            info.flag_bits = centdir[5]
            info.compress_type = centdir[6]

            #  定制化处理，MRO/MDT eNB ID提取
            match = re.search(r"_(\d{6,8})_", info.sub_file_name)
            if match:
                info.enodebid = match.group(1)
            else:
                info.enodebid = 0
            file_info_array.append(info)
            #  使用read跳过部分无需读取的数据信息
            # _CD_EXTRA_FIELD_LENGTH = 13 // 额外字段信息
            # _CD_COMMENT_LENGTH = 14 // 注释
            data.seek(centdir[13] + centdir[14], 1)
            total = total + cd_dir_size + centdir[12] + centdir[13] + centdir[14]
        return file_info_array

    @asynccontextmanager
    async def open_file(self, file_path: str):
        """文件操作的异步上下文管理器

        Args:
            file_path: 要打开的文件路径

        Yields:
            NDSClient: 当前客户端实例
        """
        try:
            await self.open(file_path)
            yield self
        finally:
            await self.close()
            if not await self.check_connect():
                await self.connect()

    async def read_file_bytes(self, file_path: str, header_offset: int = 0, size: Optional[int] = None) -> bytes:
        """读取文件内容

        Args:
            file_path: 文件路径
            header_offset: 文件头偏移量, 默认为0
            size: 要读取的字节数, None表示读取到文件末尾

        Returns:
            bytes: 读取的字节数据

        Raises:
            NDSError: 文件读取错误
        """
        try:
            await self.open(file_path)
            await self.seek(header_offset)
            data = await self.read(size)
            await self.close()
            return data
        except Exception as e:
            raise NDSError(f"Failed to read file {file_path}: {str(e)}", level=1, nds_id=self.ID)
