# Novel 2 Script 
 
Shared-architecture skill for the multi-step novel-to-vertical-microdrama workflow. 
 
## Registration 
 
- registry entry: `skills/registry.yaml` > `id: novel2script` 
- adapter: `skill_md` 
- spec: `skills/novel2script/SKILL.md` 
 
## Resources 
 
- prompts live under `skills/novel2script/prompts/` 
- supporting references/templates live under `skills/novel2script/assets/` 
- the shared engine resolves `.md`, `.txt`, `.docx`, and `.xlsx` resources relative to the skill folder 
 
## Runtime Notes 
 
- execution stays on the shared adapter path: app > catalog > `skill_md` adapter > shared engine 
- outputs are written under `outputs/novel2script/` 
- resume follows the step metadata defined in `SKILL.md`
