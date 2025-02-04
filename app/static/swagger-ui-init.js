window.onload = function() {
  window.ui = SwaggerUIBundle({
    url: window.location.origin + "/openapi.json",
    dom_id: '#swagger-ui',
    deepLinking: true,
    presets: [
      SwaggerUIBundle.presets.apis,
      SwaggerUIBundle.SwaggerUIStandalonePreset
    ],
    plugins: [
      SwaggerUIBundle.plugins.DownloadUrl
    ],
    layout: "StandaloneLayout",
    supportedSubmitMethods: ['get', 'post', 'put', 'delete', 'patch'],
    onComplete: function() {
      ui.preauthorizeApiKey("Authorization", "Bearer " + localStorage.getItem("token"));
    }
  });
}
