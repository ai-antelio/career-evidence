"""Linux resource-limited parser subprocess; not a malware sandbox."""
import sys, resource, json
resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU, (30,30))
from .extraction import parse
try:
    print(json.dumps({'text':parse(sys.stdin.buffer.read(5*1024*1024+1), sys.argv[1])}))
except Exception:
    print(json.dumps({'error':'Unable to parse this document. Use a readable PDF or DOCX.'}))
