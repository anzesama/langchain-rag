import re

with open('D:/class/project-config/langchain-rag/scripts/clean_wiki_entities_v2.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed_lines = []
for line in lines:
    # 修复 entity["id"] 问题
    line = line.replace('entity["id"]', 'entity_id')

    # 修复 llm_result.get 问题
    line = re.sub(r'len\(llm_result\.get\("valid", \[\]\)\)', 'len(valid_list)', line)
    line = re.sub(r'len\(llm_result\.get\("invalid", \[\]\)\)', 'len(invalid_list)', line)
    line = re.sub(r'llm_result\.get\("valid", \[\]\)', 'valid_list', line)
    line = re.sub(r'llm_result\.get\("invalid", \[\]\)', 'invalid_list', line)

    fixed_lines.append(line)

with open('D:/class/project-config/langchain-rag/scripts/clean_wiki_entities_v2.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print('已修复语法错误')
