import { test, expect } from "bun:test";
import { notesTools } from "../src/tools/productivity.ts";

test("private note content passes over stdin, never argv or environment", async () => {
  const original=Bun.spawn;
  let captured: { argv:string[], stdin?:Blob, env?:Record<string,string|undefined> } | undefined;
  Bun.spawn=((argv:string[],options:{stdin?:Blob,env?:Record<string,string|undefined>})=>{
    captured={argv,stdin:options.stdin,env:options.env};
    return { stdout:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(JSON.stringify({success:false,error:{code:"locked",message:"Locked"}})));c.close();}}),stderr:new ReadableStream({start(c){c.close();}}),exited:Promise.resolve(1),kill(){} };
  }) as typeof Bun.spawn;
  try {
    const result=await notesTools.find(t=>t.name==="notes_create")!.run({folder_id:"f",request_key:"k",title:"Private title",body_text:"Private content"});
    expect(captured?.argv.slice(-1)).toEqual(["notes_create"]);
    expect(JSON.stringify(captured?.argv)).not.toContain("Private");
    expect(JSON.stringify(captured?.env)).not.toContain("Private content");
    expect(JSON.parse(await captured!.stdin!.text()).body_text).toBe("Private content");
    expect((result.structuredContent.error as {code:string}).code).toBe("locked");
  } finally {Bun.spawn=original;}
});
