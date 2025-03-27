from header import *

def main():
    url = "https://www.kotak.com/bank/mailers/intrates/get_all_variable_data_latest.php?section=NRO_Term_Deposit"
    def get_html(url):
        response = requests.get(url)
        html_content = response.text
        return BeautifulSoup(html_content, 'html.parser')

    soup = get_html(url)
    company=soup.find_all('td',class_='td_wht')

    name = []
    Less_than = []
    start_days = []
    end_days = []

    ind = 5
    company = soup.find_all('td')

    # Mapping of day ranges to corresponding start and end values
    day_ranges = {
        '7 - 14 Days': (7, 14),
        '15 - 30 Days': (15, 30),
        '31 - 45 Days': (31, 45),
        '46 - 90 Days': (46, 90),
        '91 - 120 Days': (91, 120),
        '121 - 179 days': (121, 179),
        '180 Days': (180, 180),
        '181 Days to 269 Days': (181, 269),
        '270 Days': (270, 270),
        '271 Days to 363 Days': (271, 363),
        '364 Days': (364, 364),
        '365 Days to 389 Days': (365, 389),
        '390 Days (12 months 25 days)': (390, 390),
        '391 Days - Less than 23 Months': (391, 690),  # Assuming 23 months = 690 days
        '23 Months': (690, 690),
        '23 months 1 Day- less than 2 years': (691, 730),
        '2 years- less than 3 years': (730, 1095),
        '3 years and above but less than 4 years': (1095, 1460),
        '4 years and above but less than 5 years': (1460, 1825),
        '5 years and above upto and inclusive of 10 years': (1825, 3650)
    }
    idx = 1

    for i in company:
        # Skip unwanted values
        if i.text in day_ranges or ind in [3, 4]:
            ind -= 1
            continue

        # Collect the name and Less_than values for each range
        if ind == 2:
            name.append(i.text)
            ind -= 1
        elif ind == 1:
            Less_than.append(i.text)
            ind = 5
            idx+=1
    # Now add the start and end columns based on the ranges
    for key in day_ranges.keys():
        start, end = day_ranges[key]
        start_days.append(start)
        end_days.append(end)

    # Create the DataFrame
    df = pd.DataFrame({
        "ID": [i for i in range(1,idx)],
        'tenure_start': start_days, 
        'tenure_end': end_days,
        'rate': Less_than,
    })
    # Remove percentage sign from the 'name' column
    df['rate'] = df['rate'].str.replace('%', '', regex=False)

    data_to_insert = df.to_dict(orient='records')
    supabase = create_client(URL,KEY)
    print("-"*20)
    try:
        for record in data_to_insert:
                    res = supabase.table("KOTAK").update({
                        'tenure_start': record['tenure_start'],
                        'tenure_end': record['tenure_end'],
                        'rate': record['rate']
                    }).eq('ID', record['ID']).execute()
        print("KOTAK  |  updating KOTAK data ✅")
    except Exception as e: 
        print("KOTAK  |  Failed updating KOTAK data ❌")
        print(e)
    print("-"*20)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(1)


