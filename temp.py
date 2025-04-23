import subprocess
import threading
import time
path1 = "RAG"  # Set this to the directory where you want to run the script

def run_subprocess():
    # This will run the process in a subprocess
    subprocess.run(["python", "updater.py"] , cwd = "updater")

# Create a thread to run the subprocess
thread = threading.Thread(target=run_subprocess)

# Start the thread
thread.start()

r = 1
while r<10e7 :
    print(r)
    time.sleep(1)
    r+=1

thread.join()

