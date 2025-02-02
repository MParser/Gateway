import os
import uvicorn
from app.core.config import config

if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear') 
    uvicorn.run(
        "app.init:app",
        host=config.get("app.host", "0.0.0.0"),
        port=config.get("app.port", 8000),
        reload=config.get("app.reload", False)
    )