from subprocess import run
from time import sleep
import os,logging

logger=logging.getLogger('logger')

# Path and name to the script you are trying to start
supervisee_path = "/home/pi/Pi-ro-safe/main.py"

while True:
    try:
        os.chdir('/home/pi/Pi-ro-safe')
        run("python "+supervisee_path,shell=True, check=True,cwd=os.getcwd())
        break #if graceful exit we stop supervising
    except:
        pass #if ungraceful exit we continue supervising
