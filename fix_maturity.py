import re

# Fix block-registry.ts
with open('frontend/src/lib/block-registry.ts', 'r') as f:
    text = f.read()

# We need to find block objects in CORE_BLOCKS and add maturity: 'stable' if missing.
# A block usually starts with { \n type: '...',
# Let's just use regex to insert maturity after category or accent

def repl(match):
    block = match.group(0)
    if 'maturity:' not in block:
        # insert after type: '...' string
        return re.sub(r"(type:\s*'[^']+',)", r"\1\n    maturity: 'stable',", block, count=1)
    return block

# Find all objects starting with { type: '
new_text = re.sub(r"\{\s*type:\s*'[^']+',[\s\S]*?(?=\n  \},|\n  \})", repl, text)
new_text = new_text.replace("maturity: 'stable',\n    maturity: 'stable',", "maturity: 'stable',")

with open('frontend/src/lib/block-registry.ts', 'w') as f:
    f.write(new_text)

# Fix WorkshopView.tsx
with open('frontend/src/views/WorkshopView.tsx', 'r') as f:
    wt = f.read()

wt = wt.replace("isCustom: true,", "isCustom: true,\n      maturity: 'stable',")

with open('frontend/src/views/WorkshopView.tsx', 'w') as f:
    f.write(wt)
