// SPDX-License-Identifier: GPL-3.0-only
import { mkdir, copyFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const root = new URL('../../', import.meta.url)
const destination = new URL('../public/legal/', import.meta.url)
await mkdir(destination, { recursive: true })
for (const [name, target] of [['LICENSE', 'LICENSE.txt'], ['NOTICE', 'NOTICE.txt'], ['THIRD_PARTY_NOTICES.txt', 'THIRD_PARTY_NOTICES.txt']]) {
  await copyFile(fileURLToPath(new URL(name, root)), fileURLToPath(new URL(target, destination)))
}
