// Herramienta de documentación; requiere @viz-js/viz y sharp.
// NODE_PATH puede señalar el directorio de módulos del entorno de generación.
const fs = require('fs');
const path = require('path');
const {instance} = require('@viz-js/viz');
const sharp = require('sharp');
(async () => {
  const viz = await instance();
  const folder = path.resolve(__dirname, '../docs/diagramas');
  for (const name of ['c4_nivel_1','c4_nivel_2','c4_nivel_3']) {
    const svg = viz.renderString(fs.readFileSync(path.join(folder,name+'.dot'),'utf8'), {format:'svg',engine:'dot'});
    fs.writeFileSync(path.join(folder,name+'.svg'),svg);
    await sharp(Buffer.from(svg), {density:220}).png().toFile(path.join(folder,name+'.png'));
  }
})();
