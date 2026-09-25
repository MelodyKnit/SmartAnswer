import { createHash } from 'node:crypto'
import { readdir, readFile, stat } from 'node:fs/promises'
import path from 'node:path'

const projectRoot = process.cwd()
const frontendRoot = path.join(projectRoot, 'src', 'website')
const fixedFiles = [
  'package.json',
  'package-lock.json',
  'vite.config.ts',
  'tsconfig.json',
  'tsconfig.app.json',
  'tsconfig.node.json',
  'index.html',
]

async function collectFiles(relativeDirectory) {
  const directory = path.join(frontendRoot, relativeDirectory)
  const entries = await readdir(directory, { withFileTypes: true })
  const files = []
  for (const entry of entries) {
    const relativePath = path.join(relativeDirectory, entry.name)
    if (entry.isDirectory()) {
      files.push(...await collectFiles(relativePath))
    } else if (entry.isFile()) {
      files.push(relativePath)
    }
  }
  return files
}

async function fileHash(relativePath) {
  const content = await readFile(path.join(frontendRoot, relativePath))
  return createHash('sha256').update(content).digest('hex')
}

const inputFiles = [...fixedFiles]
for (const directory of ['src', 'public']) {
  inputFiles.push(...await collectFiles(directory))
}
inputFiles.sort()

const manifest = []
for (const relativePath of inputFiles) {
  const normalizedPath = relativePath.split(path.sep).join('/')
  await stat(path.join(frontendRoot, relativePath))
  manifest.push(`${normalizedPath}\t${await fileHash(relativePath)}`)
}

process.stdout.write(`${createHash('sha256').update(`${manifest.join('\n')}\n`).digest('hex')}\n`)
