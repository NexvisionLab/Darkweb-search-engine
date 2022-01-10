import os

privateDirectory = os.environ['ETCDIR'] + "/private/"

if not os.path.exists(privateDirectory):
    os.mkdir(privateDirectory)
    print("Directory " , privateDirectory ,  " Created ")
else:
    print("Directory " , privateDirectory ,  " already exists")

PATH = os.environ['ETCDIR'] + "/private/flask.secret"
secret=os.urandom(32)
file = open(PATH, "w")
while('"' in secret.encode("string-escape") or '`' in secret.encode("string-escape")):
    secret=os.urandom(32)
file.write('FLASK_SECRET="%s"\n' % secret.encode("string-escape"))
print("Written flask secret to '%s'" % PATH)
