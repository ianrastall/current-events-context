import os
import re

# --- Configuration ---
repo_root = r"D:\GitHub\current-events-context"
md_base_dir = os.path.join(repo_root, "reference", "deep-research")
output_dir = os.path.join(repo_root, "copilot_prompts")
template_path = os.path.join(repo_root, "llm_agent_prompt.txt") # Your master instruction file

size_threshold_kb = 10 
pattern = re.compile(r"^\d{4}-\d{2}-\d{2}[a-zA-Z]?$")

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

# Read the master prompt template
try:
    with open(template_path, 'r', encoding='utf-8') as t_file:
        master_template = t_file.read()
except FileNotFoundError:
    print(f"Error: Could not find the prompt template at {template_path}")
    exit(1)

stub_count = 0
print("Scanning directories and building self-contained agent prompts...")

for root, dirs, files in os.walk(md_base_dir):
    for file in files:
        if file.endswith(".md"):
            base_name = os.path.splitext(file)[0]
            
            if pattern.match(base_name):
                md_full_path = os.path.join(root, file)
                clean_name = re.sub(r'[a-zA-Z]$', '', base_name) # e.g., 2026-03-07
                
                # Calculate parallel YAML path
                rel_dir = os.path.relpath(root, md_base_dir)
                yaml_folder = repo_root if rel_dir == '.' else os.path.join(repo_root, rel_dir)
                yaml_path = os.path.join(yaml_folder, f"{clean_name}.yaml")
                
                # Check if YAML exists and is a stub
                if os.path.exists(yaml_path):
                    size_kb = os.path.getsize(yaml_path) / 1024.0
                    
                    if size_kb < size_threshold_kb:
                        # 1. Read the actual Markdown content
                        with open(md_full_path, 'r', encoding='utf-8') as md_file:
                            md_content = md_file.read()
                        
                        # 2. Inject data into the template
                        # Replaces the placeholders defined in your llm_agent_prompt.txt
                        final_prompt = master_template.replace(
                            "DATE_ISO = [insert date]", 
                            f"DATE_ISO = {clean_name}"
                        )
                        final_prompt = final_prompt.replace(
                            "[Insert Markdown Report Here]", 
                            md_content
                        )
                        
                        # Add a final directive pointing to the target YAML file
                        final_prompt += f"\n\n*** TARGET OUTPUT FILE ***\nPlease save the generated YAML to: {yaml_path}"
                        
                        # 3. Write the self-contained prompt to disk
                        prompt_output_path = os.path.join(output_dir, f"agent_prompt_{clean_name}.txt")
                        with open(prompt_output_path, 'w', encoding='utf-8') as out_file:
                            out_file.write(final_prompt)
                            
                        print(f"Built complete prompt for {clean_name} ({size_kb:.2f} KB stub)")
                        stub_count += 1
                else:
                    print(f"Notice: Missing YAML equivalent for {file} in {yaml_folder}")

print(f"\nSuccess. Generated {stub_count} agent-ready prompts in {output_dir}.")