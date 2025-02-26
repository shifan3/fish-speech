from optparse import OptionParser
import urllib.parse
import requests
from multiprocessing import Pool

optparser = OptionParser()
optparser.add_option("-n", "--nworkers", type=int)
optparser.add_option("-u", "--url", type=str)

opts, args = optparser.parse_args()

def work(_):
    text = text = urllib.parse.quote("hello world")
    url = f"{opts.url}?text={text}"
    resp = requests.get(url, timeout=1000000)
    return resp.status_code

with Pool(opts.nworkers) as pool:
    codes = pool.map(work, range(opts.nworkers))

if any(code != 200 for code in codes):
    raise Exception("Code != 200, warmup failed")

    