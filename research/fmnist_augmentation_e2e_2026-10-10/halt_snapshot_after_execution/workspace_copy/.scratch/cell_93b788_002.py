
with open('src/train.py', 'r') as f:
    content = f.read()
# Print the main function
idx = content.find('def main()')
print(content[idx:idx+3000])
