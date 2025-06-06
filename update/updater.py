from update.hdfc import main as hdfc
from update.icici import main as icici
from update.sbi import main as sbi
from update.kotak import main as kotak
from  update.header import * 

def main():
        try:
            hdfc()
        except Exception as e:
            print("HDFC  |  Failed updating HDFC data | UNREACHABLE [X]")
        try:
            sbi()
        except Exception as e:
            print("SBI  |  Failed updating SBI data | UNREACHABLE [X]")
        try:
            kotak()
        except Exception as e:
            print("KOTAK  |  Failed updating KOTAK data | UNREACHABLE [X]")
        try:
            icici()
        except Exception as e:
            print("ICICI  |  Failed updating ICICI data | UNREACHABLE [X]")

