// Test screenshots contain generated/fake scenes and stay in private scratch.
// Respect TMPDIR so constrained environments need not write directly to /tmp.
import {lstatSync,mkdirSync} from 'node:fs'
import {basename,join,resolve} from 'node:path'
import {tmpdir} from 'node:os'

const directory=resolve(process.env.E2E_ARTIFACT_DIRECTORY||join(tmpdir(),'echelon-browser-artifacts'))
export function testArtifact(name){
 if(typeof name!=='string'||name!==basename(name)||name.includes('\\')||name.includes('\0'))throw new Error('Test artifact must be a filename')
 mkdirSync(directory,{recursive:true,mode:0o700})
 const stat=lstatSync(directory)
 if(!stat.isDirectory()||stat.isSymbolicLink()||stat.uid!==process.getuid()||(stat.mode&0o077))throw new Error('Use a private owned test-artifact directory')
 return join(directory,name)
}
