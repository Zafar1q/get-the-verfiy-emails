import streamlit as st
import pandas as pd
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import smtplib
import dns.resolver

# ---------------------- Email Extraction Functions ---------------------- #
def extract_emails_from_text(text):
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(email_pattern, text)
    cleaned_emails = [re.sub(r'[^a-zA-Z0-9@._-]', '', email.split(' ')[0]) for email in emails]
    return list(set(cleaned_emails))

def get_page_text(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return " ".join(soup.stripped_strings)
    except:
        return ""

def find_contact_page(main_url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        response = requests.get(main_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        contact_patterns = [
            'contact', 'contact-us', 'contactus', 'contact.html',
            'contact.php', 'contact.asp', 'contact.aspx', 'contact/',
            'about/contact', 'company/contact', 'connect', 'reach-us'
        ]

        possible_links = []
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            text = a.get_text().lower()
            if any(p in href for p in contact_patterns) or any(w in text for w in ['contact', 'email', 'reach us']):
                possible_links.append(urljoin(main_url, a['href']))

        return list(set(possible_links))[:3]
    except:
        return []

def extract_all_emails(domain):
    emails = []
    homepage_text = get_page_text(domain)
    emails.extend(extract_emails_from_text(homepage_text))

    if not emails:
        contact_pages = find_contact_page(domain)
        for page in contact_pages:
            text = get_page_text(page)
            emails.extend(extract_emails_from_text(text))
            if emails:
                break

    return list(set(emails))

# ---------------------- Email Verifier Functions ---------------------- #
def get_mx_record(domain):
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return str(records[0].exchange)
    except:
        return None

def verify_email(email):
    try:
        domain = email.split('@')[1]
        mx = get_mx_record(domain)
        if not mx:
            return "❌ Domain Not Found"

        server = smtplib.SMTP(timeout=10)
        server.connect(mx)
        server.helo()
        server.mail('test@example.com')  # Fake sender
        code, _ = server.rcpt(email)
        server.quit()

        if code in [250, 251]:
            return "✅ Exists / Good"
        else:
            return "❌ Doesn't Exist"
    except:
        return "⚠️ Error"

# ---------------------- Streamlit UI ---------------------- #
st.set_page_config("Email Extractor & Verifier", layout="centered")
st.title("📬 Email Extractor & Verifier Tool")

tool_option = st.radio("Choose a tool:", ["Email Finder", "Email Verifier"])

# ---------------------- Email Finder Section ---------------------- #
if tool_option == "Email Finder":
    st.subheader("🔎 Email Finder Tool")
    input_method = st.radio("Choose an input method:", ["Enter a Domain", "Upload a CSV File"])

    if input_method == "Enter a Domain":
        domain_input = st.text_input("Enter full domain (e.g., https://example.com)")
        if st.button("Extract Emails"):
            if domain_input:
                with st.spinner("Extracting emails..."):
                    emails = extract_all_emails(domain_input.strip())
                    if emails:
                        st.success("Emails found:")
                        st.write(emails)
                    else:
                        st.warning("No emails found.")
            else:
                st.error("Please enter a valid domain.")

    elif input_method == "Upload a CSV File":
        uploaded_file = st.file_uploader("Upload CSV with company domains", type=["csv"])
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            st.subheader("CSV Preview")
            st.dataframe(df.head())

            column_name = st.selectbox("Select the domain column", df.columns)
            if st.button("Extract Emails from CSV"):
                cleaned_domains = df[column_name].dropna().astype(str).apply(
                    lambda x: f"https://{x}" if not x.startswith("http") else x
                ).tolist()

                progress = st.progress(0)
                results = []

                def process_domain(domain):
                    return extract_all_emails(domain)

                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(process_domain, domain) for domain in cleaned_domains]

                    for i, future in enumerate(futures):
                        result = future.result()
                        results.append(result)
                        progress.progress((i + 1) / len(futures))

                df["Extracted Emails"] = results
                st.success("Extraction complete.")
                st.dataframe(df)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Download CSV with Emails", data=csv, file_name="emails_extracted.csv", mime="text/csv")

# ---------------------- Email Verifier Section ---------------------- #
elif tool_option == "Email Verifier":
    st.subheader("✅ Email Verifier Tool")

    # ---- Single Email ---- #
    st.markdown("### 🔹 Verify a Single Email")
    single_email = st.text_input("Enter an email address to verify")

    if st.button("Verify Now"):
        if single_email:
            with st.spinner("Verifying..."):
                result = verify_email(single_email)
            st.success(f"**Result for {single_email}:** {result}")
        else:
            st.warning("Please enter an email address.")

    # ---- Bulk Emails ---- #
    st.markdown("### 🔹 Verify Bulk Emails (CSV Upload)")
    uploaded_file = st.file_uploader("Upload CSV with email addresses", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.subheader("CSV Preview")
        st.dataframe(df.head())

        email_column = st.selectbox("Select the email column", df.columns)

        if st.button("Verify Emails"):
            email_list = df[email_column].dropna().astype(str).tolist()
            progress = st.progress(0)
            results = []

            for i, email in enumerate(email_list):
                status = verify_email(email)
                results.append(status)
                progress.progress((i + 1) / len(email_list))

            df["Verification Status"] = results
            st.success("Verification complete.")
            st.dataframe(df)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Download Verified Emails", data=csv, file_name="emails_verified.csv", mime="text/csv")
