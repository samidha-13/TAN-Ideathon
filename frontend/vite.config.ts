import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import cesium from 'vite-plugin-cesium'

export default defineConfig({
  plugins: [
    react(),
    // @ts-ignore
    cesium(),
    {
      name: 'serve-parent-dirs',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && (req.url.startsWith('/data/') || req.url.startsWith('/terrain/'))) {
            const urlPath = req.url.split('?')[0]
            const filePath = path.resolve(__dirname, '..', urlPath.slice(1))
            if (fs.existsSync(filePath)) {
              if (filePath.endsWith('.csv')) res.setHeader('Content-Type', 'text/csv')
              else if (filePath.endsWith('.json')) res.setHeader('Content-Type', 'application/json')
              else if (filePath.endsWith('.tif') || filePath.endsWith('.tiff')) res.setHeader('Content-Type', 'image/tiff')
              
              const stream = fs.createReadStream(filePath)
              return stream.pipe(res)
            } else {
              next()
              return
            }
          } else {
            next()
          }
        })
      }
    }
  ],
})
