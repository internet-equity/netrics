import subprocess as sp

def main():

    # Read config from stdin
    params = json.load(sys.stdin)
    res = {}




    cmd = "speedtest --accept-license -f json -u Mbps"

if __name__ == '__main__':
    main()
