import pyperclip
f = open("tmpfile", "r")
pasteable = f.read()
print(pasteable)
print("Results have been loaded to clipboard, just paste them to the excel sheet.")
pyperclip.copy(pasteable)
