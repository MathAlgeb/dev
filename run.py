import psutil as ps
from subprocess import PIPE

cmd = ["python3", "utils/sub.py"]
l = []
def test():
    for i in range(10):
        process = ps.Popen(cmd, stdout=PIPE)
        print(process.is_running())
        mem = (process.memory_full_info().rss / (1000 * 1000))
        print("non-swapped physical memory a process has used: {} MB".format(mem)) 
        print(process.pid)
        l.append(process)
        print(process.status())
        print("iteration: {} done".format(i+1))
        output = process.communicate()[0]
        print(output)
test()
