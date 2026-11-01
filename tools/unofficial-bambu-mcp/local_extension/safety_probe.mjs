// Read-only adapter to the already installed printer/file validation library.
// This program contains no upload, start, stop, heating or other mutation route.
import path from 'node:path';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
import {inspectPrintFile} from '../../bambu-printer-mcp/dist/safety/print-file.js';
import {BambuImplementation} from '../../bambu-printer-mcp/dist/printers/bambu.js';
import {validatePrinterState} from '../../bambu-printer-mcp/dist/safety/printer-state.js';

let request;
try { request = JSON.parse(fs.readFileSync(0, 'utf8')); }
catch { process.stdout.write(JSON.stringify({ok:false,error:'Invalid JSON request'})); process.exit(1); }
let printer;
let token = '';
const output = value => process.stdout.write(JSON.stringify(value));
try {
  if (!['inspect', 'status', 'preflight'].includes(request.op)) throw Error('Read-only operation required');
  let artifact;
  if (request.op !== 'status') {
    artifact = await inspectPrintFile(request.file_path, {
      model:'p1s', nozzleDiameters:[0.4], plateIndex:0, bedType:'textured_plate',
    });
    if (artifact.materials.length !== 1) throw Error('Studio submission currently supports one external-spool material');
    artifact = {...artifact, nozzle_diameter:artifact.nozzleDiameters[0], material:artifact.materials[0],
      bed_temperature:artifact.maxBedTemperature,
      job_name:path.basename(request.file_path).replace(/\.3mf$/i, '')};
  }
  if (request.op === 'inspect') output({ok:true,artifact});
  else {
    const envFile=path.join(process.env.LOCALAPPDATA, 'BambuPrinterMCP', 'printer.env');
    process.loadEnvFile(envFile);
    const host=process.env.BAMBU_PRINTER_HOST || process.env.PRINTER_HOST;
    const serial=process.env.BAMBU_PRINTER_SERIAL || process.env.BAMBU_SERIAL;
    token=process.env.BAMBU_PRINTER_ACCESS_TOKEN || process.env.BAMBU_TOKEN || '';
    if(!host || !serial || !token) throw Error('Existing printer connection is incomplete');
    if(request.printer_serial && request.printer_serial !== serial) throw Error('Requested printer does not match the configured connection');
    printer=new BambuImplementation();
    const status=await printer.getSafetyStatus(host,serial,token);
    const raw=status.raw;
    const summary={read_at:status.observation.receivedAt/1000,state:raw.gcode_state,
      serial:status.observedSerial || status.serial, model:status.model,
      identity_source:status.observation.identitySource,
      nozzle_diameter:Number(raw.nozzle_diameter), material:raw.vt_tray?.tray_type,
      errors:[...(raw.hms || []), ...(raw.print_error ? [{print_error:raw.print_error}] : [])],
      job_name:raw.subtask_name || raw.gcode_file || '', progress:raw.mc_percent,
      bed:{actual:raw.bed_temper,target:raw.bed_target_temper},
      nozzle:{actual:raw.nozzle_temper,target:raw.nozzle_target_temper}};
    if (request.op==='preflight') {
      validatePrinterState(status,{model:artifact.model,nozzleDiameters:artifact.nozzleDiameters,
        materials:artifact.materials,usedFilamentPositions:artifact.usedFilamentPositions,
        requireIdle:true,useAMS:false,nozzleTypes:artifact.nozzleTypes,nozzleFlows:artifact.nozzleFlows});
    }
    output({ok:true,artifact,printer:summary});
  }
} catch(error) {
  let message=String(error.message || error);
  if(token) message=message.split(token).join('[redacted]');
  output({ok:false,error:message}); process.exitCode=1;
} finally {
  if(printer) await printer.disconnectAll();
}
