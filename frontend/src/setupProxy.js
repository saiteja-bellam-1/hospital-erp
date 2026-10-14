const fs = require('fs');
const path = require('path');

// Serve the introduction page at the dev-server home URL.
// Login and the hospital app stay on their own routes.
const siteIndex = path.join(__dirname, '../public/website/index.html');

module.exports = function setupProxy(app) {
  app.get('/', (req, res, next) => {
    if (!fs.existsSync(siteIndex)) {
      next();
      return;
    }
    res.sendFile(siteIndex);
  });

  app.get(['/website', '/website/'], (req, res) => {
    res.redirect(307, '/');
  });
};
