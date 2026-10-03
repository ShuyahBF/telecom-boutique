import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import path from 'node:path'
import { execSync } from 'node:child_process'

// Code court du commit déployé (7 caractères), calculé à la compilation :
//  1. sur Render, la variable RENDER_GIT_COMMIT contient le commit complet ;
//  2. sinon (poste de développement), on le demande à git ;
//  3. à défaut (pas de git), on affiche « local ».
// Il est affiché à côté de la version et du lot (voir src/version.js).
function commitCourt() {
  const render = process.env.RENDER_GIT_COMMIT
  if (render) return render.slice(0, 7)
  try {
    return execSync('git rev-parse --short=7 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return 'local'
  }
}

// Alias "@" = dossier src (imports plus lisibles : "@/lib/api")
export default defineConfig({
  plugins: [react()],
  // Constantes remplacées dans le code au moment de la compilation
  // (lues par src/version.js) : commit court et date/heure UTC de compilation.
  define: {
    __ADLYN_COMMIT__: JSON.stringify(commitCourt()),
    __ADLYN_DATE_COMPILATION__: JSON.stringify(new Date().toISOString()),
  },
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    host: true,
    port: 5173,
  },
})
