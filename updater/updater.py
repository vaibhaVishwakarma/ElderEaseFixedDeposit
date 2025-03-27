from hdfc import main as hdfc
from icici import main as icici
from sbi import main as sbi
from kotak import main as kotak
from header import *
while True:
    try:
        hdfc()
    except Exception as e:
        print("HDFC  |  Failed updating HDFC data | UNREACHABLE ❌")
    try:
        sbi()
    except Exception as e:
        print("SBI  |  Failed updating SBI data | UNREACHABLE ❌")
    try:
        kotak()
    except Exception as e:
        print("KOTAK  |  Failed updating KOTAK data | UNREACHABLE ❌")
    try:
        icici()
    except Exception as e:
        print("ICICI  |  Failed updating ICICI data | UNREACHABLE ❌")

    time.sleep(30*MINUTES)
