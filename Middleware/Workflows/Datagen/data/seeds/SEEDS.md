# Seed artifacts (F016 — real artifact seeding)

Real public loan documents, regulator directions and complaint data that
the generator's terminology comes from. Every term, rate range and
checklist item in `terminology.yaml` traces to one of these artifacts
by its seed ID (for example `SBI-MITC-01`).

- **Fetched:** 2026-11-12 (all dates below are the fetch date).
- **Rule:** no raw PDFs are stored in the repo — this manifest plus the
  extracted terminology in `terminology.yaml` only. If a source cannot
  be fetched, its terms are not used.
- **Families:** RBI Master Directions (4), SBI (5), HDFC Bank (2),
  ICICI Bank (2), PNB (1), Bank of Baroda (1), MUDRA / PMMY (2),
  MSME working capital (1), IBA (1), CFPB (2) — 21 artifacts in total.
- **Coverage:** home, personal, business, auto, education, gold, MSME.

## RBI Master Directions

### RBI-IR-01 — RBI Master Direction, Interest Rate on Advances, 2016

- **URL:** https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10295
- **Type:** Master Direction
- **Fetched:** 2026-11-12
- **Extracted:** MCLR (marginal cost of funds + negative carry on CRR +
  operating costs + tenor premium; tenors overnight / 1M / 3M / 6M / 1Y;
  monthly review), EBLR / external benchmark (repo rate, 3M / 6M T-Bill
  yields via FBIL; all new floating retail and MSME loans benchmarked
  from 1 Oct 2019), spread components (business strategy, credit risk
  premium), penal charges, monthly rests, fixed vs floating rate.

### RBI-KYC-01 — RBI Master Direction, Know Your Customer (KYC) Direction, 2016

- **URL:** https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=10292&Mode=0
- **Type:** Master Direction
- **Fetched:** 2026-11-12
- **Extracted:** Officially Valid Documents (passport, driving licence,
  Voter's Identity Card, NREGA job card, NPR letter), CKYCR (Central
  KYC Records Registry), Aadhaar as identity and address proof,
  Customer Identification Procedure, Beneficial Owner, PMLA 2002.

### RBI-PSL-01 — RBI Master Direction, Priority Sector Lending — Targets and Classification, 2025

- **URL:** https://www.rbi.org.in/scripts/BS_ViewMasDirections.aspx?id=12799
- **Type:** Master Direction
- **Fetched:** 2026-11-12
- **Extracted:** 8 priority-sector categories (Agriculture, MSME, Export
  Credit, Education, Housing, Social Infrastructure, Renewable Energy,
  Others); targets — 40% of ANBC for domestic SCBs, 18% agriculture,
  7.5% micro enterprises, 12% weaker sections; PSLCs traded on e-Kuber;
  shortfall to RIDF.

### RBI-GOLD-01 — RBI (Lending Against Gold and Silver Collateral) Directions, 2025

- **URL:** https://trackliveprice.com/blog/rbi-gold-silver-loan-directions-2026-10/
  (quotes the RBI text; consolidated text on rbi.org.in, RBI/2025-26/47,
  dated 6 June 2025, updated 29 Sep 2025)
- **Type:** Master Direction (via a page quoting the RBI text)
- **Fetched:** 2026-11-12
- **Extracted:** LTV caps for consumption loans — 85% up to Rs 2.5 lakh,
  80% above Rs 2.5 lakh to Rs 5 lakh, 75% above Rs 5 lakh; valuation at
  the lower of the 30-day average price and the previous day's closing
  price published by IBJA or a SEBI-regulated exchange; eligible
  collateral is jewellery, ornaments and coins (bullion not eligible);
  bullet repayment capped at 12 months; collateral returned within
  7 working days of full repayment (Rs 5,000 per day of delay).

## SBI

### SBI-HOME-01 — SBI home loan interest rates (official rates page)

- **URL:** https://sbi.bank.in/web/interest-rates/interest-rates/loan-schemes-interest-rates/home-loans-interest-rates-current
- **Type:** Bank rate page
- **Fetched:** 2026-11-12
- **Extracted:** Home loans 7.50% p.a. onwards (w.e.f. 15.10.2026); SBI
  Gold Loan 9.20% shown on the same page. (Page is JavaScript-heavy;
  little text was extractable, so rates are corroborated by
  SBI-MITC-01 and the bank rate pages below.)

### SBI-MITC-01 — SBI Most Important Terms and Conditions (MITC), Home Loan (official PDF)

- **URL:** https://sbi.bank.in/webapp/webfiles/uploads/files/1377606055343_HOME_LOAN_MITC.pdf
- **Type:** MITC sheet
- **Fetched:** 2026-11-12
- **Extracted:** Products covered (Home Loan, Pre-approved Home Loan,
  Yuva, Max Gain, Realty, NRI, Gram Niwas / Sahyog Niwas / Tribal Plus,
  Green Home Loan); purposes (purchase / construction / extension /
  repairs / renovation of a house, flat, plot and furnishings); LTV —
  90% up to Rs 20 lakh, 80% Rs 20–75 lakh, 75% above Rs 75 lakh;
  floating rate on daily reducing balance with monthly rests; penal
  interest 2% p.a. on the irregular amount; bounced cheque / ECS /
  SI dishonour penalty Rs 250; max tenure 30 years or age 70; no
  prepayment / pre-closure penalty; security by equitable or registered
  mortgage; conversion charge 0.56% of outstanding for fixed-to-floating
  switch; disbursement only after security documents and mortgage.

### SBI-PERS-01 — SBI Xpress Credit personal loan

- **URL:** https://www.mymoneymantra.com/sbi-xpress-credit-personal-loan
- **Type:** Bank loan page (summarising SBI's Xpress Credit terms)
- **Fetched:** 2026-11-12
- **Extracted:** Rates 11.45%–14.60% p.a. by borrower category
  (defence / central armed police 11.45%–12.95%, government /
  CPSE 11.60%–14.10%, other corporates 12.60%–14.60%); daily reducing
  balance; processing fee up to 1.50% + GST (min Rs 1,000, max
  Rs 15,000); prepayment charges 3% of the prepaid amount; penal
  interest 2% per month on overdue amounts; EMI/NMI ratio up to 50–60%;
  min net monthly income Rs 25,000; tenure 6 months to 6 years; no
  security or guarantor; documents — application form with 2 photos,
  identity and residence proof, employer identity card, 6 months' salary
  slips and bank statements, income tax return, irrevocable letter of
  authority to the salary disbursing authority.

### SBI-GOLD-01 — SBI gold loan interest rates

- **URL:** https://www.thefinancialeconomy.com/state-bank-of-india-gold-loan-interest-rate/
  (rates checked against SBI's official personal gold loan page)
- **Type:** Bank loan page (checked against SBI official page)
- **Fetched:** 2026-11-12
- **Extracted:** Bullet 12-month 9.15% p.a. (1-year MCLR 8.70% + 0.45%),
  EMI and overdraft 10.10% (1-year MCLR + 1.40%); margins 26%–35%
  (bullet 35%, EMI 28%, overdraft 26%); processing fee 0.50% (min
  Rs 500, max Rs 10,000) + GST; no prepayment or foreclosure charges;
  min loan Rs 20,000, up to Rs 50 lakh; gold coins up to 50 grams;
  KYC-only documents for compliant customers, 2 photographs; income
  documents above Rs 2.5 lakh (RBI credit-assessment threshold).

### SBI-EDU-01 — SBI education loan

- **URL:** https://www.gyandhan.com/sbi-education-loan
- **Type:** Bank loan page (SBI Global Ed-Vantage and other schemes)
- **Fetched:** 2026-11-12
- **Extracted:** Rates 9.15%–9.65% EBLR-linked (female concession 50 bps);
  Global Ed-Vantage up to Rs 3 crore, collateral covering at least 90%
  of the loan value; moratorium course duration + 6 months; repayment
  up to 15 years; processing fee Rs 11,800 + GST; no prepayment penalty
  after 6 months from disbursal; SBI Rinn Raksha insurance (GCLI / TLI)
  mandatory; documents — admission letter, fee schedule / statement of
  expenses, marksheets (10th, 12th, graduation), GRE / GMAT / TOEFL /
  IELTS scores, passport, co-applicant salary slips (3 months) and
  Form 16 / ITR (2 years), 6 months' bank statements, property
  documents with 30-year chain of ownership.

## HDFC Bank

### HDFC-HOME-01 — HDFC Bank home loan

- **URL:** https://www.paisabazaar.com/hdfc-bank/home-loan/
- **Type:** Bank loan page
- **Fetched:** 2026-11-12
- **Extracted:** Starting rate 8.00% p.a. (7.45% special), repo-linked;
  LTV up to 90% (loans up to Rs 30 lakh), 80% (Rs 30–75 lakh), 75%
  (above Rs 75 lakh); processing fee up to 0.50% or Rs 4,000 whichever
  is higher + GST (salaried), 1.50% for self-employed non-professionals;
  nil prepayment on floating-rate loans to individuals; tenure up to
  30 years; loan types — purchase, construction, improvement,
  extension, plot, balance transfer, top-up, NRI, women, rural;
  documents — PAN, salary slips, Form 16 / ITR, 6 months' bank
  statements, allotment letter / sale agreement, title deeds, approved
  plan, RERA registration.

### HDFC-PERS-01 — HDFC Bank personal loan

- **URL:** https://www.buddyloan.com/hdfc-bank-personal-loan
- **Type:** Bank loan page
- **Fetched:** 2026-11-12
- **Extracted:** Rates 9.99%–24.00% p.a. (fixed); processing fee up to
  Rs 6,500 + GST; late EMI penalty 18% p.a. + tax on the overdue
  instalment; foreclosure / part-prepayment fee 2%–4% of principal
  outstanding + GST (foreclosure after 12 EMIs; part-prepayment up to
  25% of outstanding once a year); tenure 12–72 months; loan amount
  Rs 25,000 to Rs 1 crore; eligibility — age 21–60, min salary
  Rs 25,000/month, 2 years' experience (1 year in current organisation);
  documents — Aadhaar / driving licence / passport / voter ID, income
  proof (salary slip, Form 16, 3–6 months' bank statements), photograph,
  signed application form.

## ICICI Bank

### ICICI-HOME-01 — ICICI Bank home loan

- **URL:** https://www.wishfin.com/home-loan/icici-bank
- **Type:** Bank loan page
- **Fetched:** 2026-11-12
- **Extracted:** Standard floating rates 8.50%–9.80% p.a. by loan amount
  and employment type (up to Rs 35 lakh 8.50%–9.40% salaried;
  above Rs 75 lakh 8.50%–9.65% salaried / 9.80% self-employed);
  repo-linked; fixed-rate options 9.10%–9.15% (24 months) to
  10.90%–11.20% (full term); processing fee 0.50% + taxes; max tenure
  30 years; credit score 700+ preferred; documents — PAN, Aadhaar /
  passport / voter ID / driving licence, salary slip, Form 16, 6 months'
  salary-account statements, ITR (2 years) and audited profit and loss
  / balance sheet for self-employed, agreement to sell, sale deed /
  title documents, approved building plan, encumbrance documents.

### ICICI-AUTO-01 — ICICI Bank car loan FAQs (official page)

- **URL:** https://www.icici.bank.in/personal-banking/loans/car-loan/faqs
- **Type:** Bank loan FAQ (official)
- **Fetched:** 2026-11-12
- **Extracted:** New car loan 8.35% p.a. onwards; min loan Rs 1 lakh up
  to 100% of on-road price; tenure up to 7 years (84 months);
  comprehensive insurance required; NOC issued 5–7 working days after
  final payment; submit NOC + Form 35 to the RTO to remove
  hypothecation; prepayment needs a prepayment statement, request
  letter, bank statement, PAN (if cash above Rs 50,000), RC book copy
  and insurance copy; used car 9.75% onwards, 12.25%–15.50%;
  processing fee up to Rs 8,500 + GST, documentation Rs 500 + GST;
  Form 29 / 30 (RC transfer), Form 34 (hypothecation); CIBIL 700+;
  min income Rs 25,000/month salaried.

## PNB

### PNB-HOME-01 — Punjab National Bank home loan

- **URL:** https://www.thefinancialeconomy.com/punjab-national-bank-home-loan-interest-rate/
  (checked against PNB's official retail advances rate card, RLLR / MCLR
  page and service charges page)
- **Type:** Bank loan page (checked against PNB official rate card)
- **Fetched:** 2026-11-12
- **Extracted:** Floating 7.45%–9.35% (Housing Loan for Public), priced
  as a spread over RLLR 8.35% w.e.f. 8 Oct 2026; fixed 8.45%–10.85%;
  processing fee 0.35% (min Rs 2,500, max Rs 15,000) + GST, documentation
  Rs 1,350 (both waived till 31 Dec 2026 under the Utsav campaign);
  tenure up to 30 years (15 years for repairs / renovation); margin 20%
  up to Rs 75 lakh, 25% above; security by equitable or registered
  mortgage; PNB Pride (government / paramilitary / PSU) and PNB Max
  Saver variants; no prepayment charge on floating-rate loans to
  individuals (RBI prepayment directions, from 1 Jan 2026).

## Bank of Baroda

### BOB-01 — Bank of Baroda festive campaign press release (official PDF)

- **URL:** https://bankofbaroda.bank.in/-/media/project/bob/countrywebsites/india/pdfs2/2026/26-10/media-release-english-22-11.pdf
- **Type:** Bank press release (official)
- **Fetched:** 2026-11-12
- **Extracted:** Home loans from 7.40% p.a. with 100% processing fee
  waiver; car loans from 7.85% p.a.; bob Swabhoomi plot loan; bob Green
  Wheels EV concession 0.15%; women concession 0.05%, 0.10% for
  under-40 / government / PSU / salary-account customers; MSME — bob
  Green Plug up to Rs 5 crore (EV charging), CME financing up to
  60 months, Baroda Mahila Swavalamban collateral-free loans for women
  entrepreneurs.

## MUDRA / PMMY

### MUDRA-01 — Pradhan Mantri MUDRA Yojana, official portal (mudra.org.in)

- **URL:** https://www.mudra.org.in
- **Type:** Government scheme portal (official)
- **Fetched:** 2026-11-12
- **Extracted:** PMMY launched 8 Apr 2015; loans to non-corporate,
  non-farm micro / small enterprises; four products — Shishu, Kishore,
  Tarun, TarunPlus; MUDRA is a refinancing institution and does not lend
  directly — apply via a bank / NBFC / MFI or udyamimitra.in; TarunPlus
  covers above Rs 10 lakh up to Rs 20 lakh.

### MUDRA-02 — MUDRA loan tiers, rates and documents

- **URL:** https://nextwhatbusiness.com/mudra-loan-scheme/
- **Type:** Scheme guide
- **Fetched:** 2026-11-12
- **Extracted:** Shishu up to Rs 50,000 (8.85%–10%), Kishore
  Rs 50,001–5 lakh (9%–12%), Tarun Rs 5–10 lakh (9.5%–12%), Tarun Plus
  Rs 10–20 lakh (10%–12%, only after repaying a Tarun loan); collateral
  nil for all tiers; repayment up to 5 years (Tarun Plus up to 7 years);
  2% interest subvention on prompt repayment of Shishu loans; documents
  — Aadhaar, PAN, voter ID, passport, driving licence, 2 passport-size
  photographs, Udyam Registration certificate, GST certificate / trade
  licence, 6 months' bank statements, business plan / project report
  (Kishore and Tarun), machinery quotations; MUDRA Card — a RuPay debit
  card linked to the working capital limit.

## MSME working capital

### WC-01 — Working capital loans for MSME (SBI vs PNB vs HDFC)

- **URL:** https://www.entrepreneurindia.co/blogs/working-capital-loan/
- **Type:** Bank scheme comparison (citing SBI MSME products, HDFC Bank
  business loans, PNB MSME schemes)
- **Fetched:** 2026-11-12
- **Extracted:** SBI e-Mudra / SME cash credit 8.55%–10.85% linked to
  EBLR; SBI CGTMSE loan 8.90%–11.25%; HDFC Business Growth Loan
  10.75%–22.50%; PNB MSME Sahyog 8.80%–12.50%; PNB Udyog Mitra
  9.25%–13.00%; CGTMSE collateral-free cover up to Rs 2 crore; 2%
  interest subvention for Udyam-registered units; cash credit — interest
  charged only on the amount utilised, limits renewed every 12 months;
  documents — last 2 years' ITR and audited balance sheets, GST returns
  for the last 12 months, bank statements for the last 12 months, Udyam
  Registration Certificate, KYC of promoters, one-page business profile.

## IBA

### IBA-EDU-01 — IBA Model Education Loan Scheme

- **URL:** https://gradright.com/how-to-avail-iba-model-education-loan-scheme/
- **Type:** Industry model scheme (Indian Banks' Association)
- **Fetched:** 2026-11-12
- **Extracted:** Introduced by the Indian Banks' Association in 2001
  with RBI support; rates 8%–12% p.a. linked to the bank's MCLR / base
  rate (up to 1% concession); loan up to Rs 10 lakh in India, Rs 20 lakh
  abroad (Rs 25 lakh for MBA / executive management); no collateral up
  to Rs 7.5 lakh, tangible collateral above; margin 0% up to Rs 4 lakh,
  5% in India / 15% abroad above Rs 4 lakh; moratorium — course duration
  + 6 to 12 months; simple interest during the moratorium; repayment
  5–15 years; no prepayment charges; CSIS interest subsidy for family
  income below Rs 4.5 lakh; co-borrower mandatory (parent / guardian /
  spouse); documents — admission letter with fee schedule, marksheets
  (10th, 12th, graduation), GRE / GMAT / IELTS / TOEFL scores, KYC,
  co-applicant income proof, 6 months' bank statements, property
  documents with chain of ownership for loans above Rs 7.5 lakh.

## CFPB (US consumer complaints)

### CFPB-01 — CFPB Consumer Complaint Database

- **URL:** https://www.consumerfinance.gov/data-research/consumer-complaints/
- **Type:** Complaint database (US, open government data)
- **Fetched:** 2026-11-12
- **Extracted:** Database publishes complaints sent to companies for
  response (after the company responds or after 15 days, whichever is
  first), updated daily; product taxonomy includes Mortgages, Auto
  Loans, Private Student Loans, Bank Accounts and Services, Credit
  Cards, Credit Reports and Scores, Debt Collection, Payday Loans;
  complaints are not a statistical sample and are not verified findings.
  No individual complaint narratives were copied — only the public
  product taxonomy is used.

### CFPB-API-01 — CFPB Consumer Complaints API (documentation)

- **URL:** https://bytetools.bytevancer.com/public-apis/finance/cfpb-complaints-api
- **Type:** API documentation
- **Fetched:** 2026-11-12
- **Extracted:** Base URL
  `https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1`;
  no API key required; calls must be server-side (the CDN blocks
  requests carrying an `Origin` header); fields — `product`,
  `sub_product`, `issue`, `sub_issue`, `company`, `company_response`,
  `complaint_what_happened` (narrative, only where the consumer
  consented), `date_received`, `date_sent_to_company`, `timely`,
  `state`, `zip_code`; `has_narrative=true` filters to complaints with
  a published narrative. **Caveat:** the direct API call from this
  session timed out, so no live complaint records were fetched; the
  endpoint is documented here from a page that live-tested it
  (HTTP 200 on 21 Aug 2026) and from the CFPB database page above.
