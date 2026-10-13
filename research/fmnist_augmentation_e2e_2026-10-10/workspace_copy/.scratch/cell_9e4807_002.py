
with open('src/train.py') as f:
    content = f.read()
# Print just the main function
idx = content.find('def main()')
print(content[idx:idx+4000])
