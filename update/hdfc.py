from header import *


def main():
    url = "https://www.hdfcbank.com/personal/save/deposits/fixed-deposit-interest-rate"
    soup = get_html(url)
    company=soup.find_all('td')

    name = []
    Less_than = []
    start_days = []
    end_days = []

    day_ranges = {
        '7 - 14 Days': (7, 14),
        '15 - 29 Days': (15, 29),
        '30 - 45 Days': (30, 45),
        '46 - 60 Days': (46, 60),
        '61 - 89 Days': (61, 89),
        '90 Days <= 6 Months': (90, 180),
        '6 Months 1 Day <= 9 Months': (181, 270),
        '9 Months 1 Day to < 1 Year': (271, 365),
        '1 Year to < 15 Months': (365, 455),
        '15 Months to < 18 Months': (456, 540),
        '18 Months to < 21 Months': (541, 630),
        '21 Months to 2 Years': (631, 730),
        '2 Years 1 Day to < 2 Years 11 Months': (731, 880),
        '2 Years 11 Months to 3 Years': (881, 1095),
        '3 Years 1 Day to < 4 Years 7 Months': (1096, 1550),
        '4 Years 7 Months to 5 Years': (1551, 1825),
        '4 Years 7 Months - 55 months': (1551, 1650),  # Added range
        '4 Years 7 Months 1 Day <= 5 Years': (1651, 1825),  # Added range
        '5 Years 1 Day to 10 Years': (1826, 3650)  # Added range
    }

    # Collect the names and corresponding 'Less_than' values
    idx = 1
    ind = 3
    count = 0
    str = ""
    for i in company:
        if i.text == "Interest Rates":
            break

        # Skip unwanted values
        if i.text in day_ranges or ind in [3, 2]:
            if i.text == "5 Years 1 day - 10 Years":
                str = i.text
            ind -= 1
            continue
        
        if ind == 1:
            Less_than.append(i.text)
            ind = 3
            idx += 1
        
        if str == "5 Years 1 day - 10 Years":
            count += 1
            if count == 2:
                break

    # Now add the start and end columns based on the ranges
    for key in day_ranges.keys():
        start, end = day_ranges[key]
        start_days.append(start)
        end_days.append(end)

    # Remove the last entry from Less_than to match the length
    Less_than = Less_than[0:len(Less_than)-1]

    # Check if the lengths of start_days, end_days, and Less_than are the same
    if len(start_days) == len(end_days) == len(Less_than):
        # Create the DataFrame
        df = pd.DataFrame({
            'ID': range(1, len(Less_than) + 1),  # Generate ids starting from 1
            'tenure_start': start_days, 
            'tenure_end': end_days,
            'rate': Less_than
        })
        
        # Remove percent sign from 'rate' column and convert to numeric
        df['rate'] = df['rate'].str.replace('%', '').astype(float)

        # Print the DataFrame
        # print(df)
    # else:
        # print(f"Length mismatch: start_days ({len(start_days)}), end_days ({len(end_days)}), Less_than ({len(Less_than)})")

    data_to_insert = df.to_dict(orient='records')
    supabase = create_client(URL,KEY)
    print("-"*20)
    try:
        for record in data_to_insert:
                    res = supabase.table("HDFC").update({
                        'tenure_start': record['tenure_start'],
                        'tenure_end': record['tenure_end'],
                        'rate': record['rate']
                    }).eq('ID', record['ID']).execute()
        print("HDFC  |  updating HDFC data [OK]")
    except Exception as e: 
        print("HDFC  |  Failed updating HDFC data [BAD]")
        print(e)
    print("-"*20)

if __name__ == "__main__":
    while True:
        main()
        time.sleep(1)


