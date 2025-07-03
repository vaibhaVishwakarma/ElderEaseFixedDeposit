from header import *

def main():
    url = "https://sbi.co.in/web/interest-rates/deposit-rates/retail-domestic-term-deposits"
    soup = get_html(url)
    t_body = soup.find("tbody").findAll("tr")


    def convert_to_days(inp):
        inp = inp.lower()
        n = int(re.findall(r"\d+" , inp)[0])
        if "day" in inp: return n
        if "month" in inp : return n*30
        return n*365

    df = pd.DataFrame()
    iD = 0
    for i in t_body:
        cols = i.findAll("td")  
        nums = re.findall(r"\d+\s\w*",cols[0].text)
        row = {"ID": iD+1 ,"tenure_start" : [convert_to_days(nums[0])] , "tenure_end" : [convert_to_days(nums[1])] , "rate" : [float(re.findall(r"\d+.\d+" , cols[-1].text)[0])] }
        df = pd.concat([df , pd.DataFrame(row)] ,ignore_index=True)
        iD+=1
    data_to_insert = df.to_dict(orient='records')
    
    supabase = create_client(URL,KEY)

    print("-"*20)
    try:
        for record in data_to_insert:
            res = supabase.table("SBI").update({
                'tenure_start': record['tenure_start'],
                'tenure_end': record['tenure_end'],
                'rate': record['rate']
            }).eq('ID', record['ID']).execute()
        print("SBI  |  updating SBI data [OK]")
    except Exception as e: 
        print("SBI  |  Failed updating SBI data [BAD]")
        print(e)
    print("-"*20)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(60*MINUTES)


