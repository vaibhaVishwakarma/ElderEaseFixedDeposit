from header import *

def main():
    # Set up options for headless mode
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")

    # Initialize WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Load the page
    url = "https://www.centralbankofindia.co.in/en/interest-rates-on-deposit"
    driver.get(url)

    time.sleep(3)  # Adjust based on hydration time

    sp = driver.page_source
    soup = BeautifulSoup(sp, 'html.parser')



    # Close browser
    driver.quit()

    def convert_to_days(inp):
        inp = inp.lower()
        nums = re.findall(r"\d+\s\w*",inp)
        n1 , n2 = re.findall(r"\d+" , inp)
        factor = 365
        if "day" in inp or "d" in inp: factor = 1
        if "month" in inp or "mn" in inp : factor = 30

        return int(n1)*factor , int(n2)*factor
        

    rows = soup.find_all("tbody")[3].find_all(class_ = "table-parent")[0].find("tbody").find_all("tr")[3:] 

    df = pd.DataFrame()
    iD = 0
    for i in rows:
        cols = i.findAll("td")  
        nums = convert_to_days(cols[0].text)
        # print(nums)
        row = {"ID": iD+1 ,"tenure_start" : [nums[0]] , "tenure_end" : [nums[1]] , "rate" : [float(re.findall(r"\d+.\d+" , cols[-1].text)[0])] }
        df = pd.concat([df , pd.DataFrame(row)] ,ignore_index=True)
        iD+=1
    data_to_insert = df.to_dict(orient='records')

    supabase = create_client(URL,KEY)

    print("-"*20)
    try:
        for record in data_to_insert:
            res = supabase.table("ICICI").update({
                'tenure_start': record['tenure_start'],
                'tenure_end': record['tenure_end'],
                'rate': record['rate']
            }).eq('ID', record['ID']).execute()
        print("ICICI  |  updating ICICI data [OK]")
    except Exception as e: 
        print("ICICI  |  Failed updating ICICI data [BAD]")
        print(e)
    print("-"*20)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(60*MINUTES)