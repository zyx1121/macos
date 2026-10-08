import { platform } from "node:os";
import { z } from "zod";
import { envelopeOutput } from "../core/schema.ts";
import { runScript } from "../core/exec.ts";
import { selectRunnableTools, type ToolboxTool } from "../core/tool.ts";
import { evaluateRequirements } from "../core/requires.ts";
export function capabilitiesTool(tools:ToolboxTool[]):ToolboxTool {
 return {name:"macos_get_capabilities",description:"Inspect tool availability, missing dependencies and noninteractive native permission status for this host. Includes hidden tools and remediation; never requests permission or launches apps.",inputSchema:{},outputSchema:envelopeOutput(z.object({platform:z.string(),tools:z.array(z.object({name:z.string(),available:z.boolean(),missing:z.array(z.string())})),permissions:z.record(z.string(),z.string()),permission_probe_error:z.string().nullable(),hints:z.array(z.string())})),annotations:{readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:false},async run(){
  const selected=await selectRunnableTools(tools);
  let permissions:Record<string,string>={},permission_probe_error:string|null=null;
  if(platform()==="darwin" && (await evaluateRequirements(["binary:uv"])).ok){
   const probe=await runScript({script:"productivity.py",args:["macos_get_permissions"],stdin:"{}",envelope:true,timeoutMs:15000});
   const content=probe.structuredContent as {data?:Record<string,string>;error?:{message?:string}}|undefined;
   if(probe.isError)permission_probe_error=content?.error?.message??"Permission probe failed";else permissions=content?.data??{};
  }else permission_probe_error=platform()==="darwin"?"uv is missing":"Native permissions require macOS";
  const hidden=new Map(selected.hidden.map(t=>[t.tool,t.failed]));
  return {isError:false,structuredContent:{data:{platform:platform(),tools:[...tools.map(t=>({name:t.name,available:!hidden.has(t.name),missing:hidden.get(t.name)??[]})),{name:"macos_get_capabilities",available:true,missing:[]}],permissions,permission_probe_error,hints:["Availability checks dependencies, not native authorization.","Grant Calendar/Reminders full access and app Automation in System Settings > Privacy & Security.","Permission probes run without prompts; unknown or target_not_running is not a permission grant.","Native operations use the MCP host identity; terminal and app-host permissions may differ."]},metadata:{schema_version:"v2"}}};
 }};
}
