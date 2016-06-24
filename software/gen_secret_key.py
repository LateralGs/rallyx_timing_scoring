import os

with open("secret_key.py","w") as skf:
  secret_key = os.urandom(24)
  skf.write("secret_key = %r" % secret_key)

