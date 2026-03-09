#!/usr/bin/env python3
"""
Scaffolds missing backend blocks based on the frontend block-registry.ts.
Usage: python scripts/scaffold_blocks.py
"""

import os
import re

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    frontend_registry = os.path.join(base_dir, "frontend", "src", "lib", "block-registry.ts")
    backend_blocks_dir = os.path.join(base_dir, "blocks")

    if not os.path.exists(frontend_registry):
        print(f"Error: Could not find {frontend_registry}")
        return

    with open(frontend_registry, "r") as f:
        content = f.read()

    blocks = []
    
    # Simple parsing using regex block by block
    # This splits the file by '{' to approximate objects
    for chunk in content.split("{"):
        type_match = re.search(r"type:\s*'([^']+)'", chunk)
        cat_match = re.search(r"category:\s*'([^']+)'", chunk)
        name_match = re.search(r"name:\s*'([^']+)'", chunk)
        
        if type_match and cat_match and name_match:
            # Check if this type wasn't already added (since split might cause overlaps or config types)
            # The config types are just strings like `type: 'string'`, without a category typically.
            blocks.append({
                "type": type_match.group(1),
                "category": cat_match.group(1),
                "name": name_match.group(1)
            })

    # deduplicate
    blocks = {b["type"]: b for b in blocks}.values()

    created = 0
    for b in blocks:
        block_dir = os.path.join(backend_blocks_dir, b["category"], b["type"])
        run_py = os.path.join(block_dir, "run.py")
        
        if not os.path.exists(run_py):
            os.makedirs(block_dir, exist_ok=True)
            template = f'"""\n{b["name"]} — Auto-generated block stub.\n"""\n\n'
            template += "def run(ctx):\n"
            template += f'    ctx.log_message("Running {b["name"]} block")\n'
            template += '    # TODO: Implement block logic\n'
            template += '    # config = ctx.config\n'
            template += '    # inputs = ctx.inputs\n'
            template += '    # ctx.save_output("port", data)\n'
            template += '    pass\n'
            
            with open(run_py, "w") as f:
                f.write(template)
            created += 1
            print(f"Scaffolded {b['category']}/{b['type']}")

    print(f"\nScaffolding complete. Created {created} new block stubs.")

if __name__ == "__main__":
    main()
