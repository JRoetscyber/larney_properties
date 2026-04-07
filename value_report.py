from fpdf import FPDF
from datetime import datetime
import matplotlib.pyplot as plt
import os

# --- BRAND COLORS (RGB for FPDF, Hex for Matplotlib) ---
NAVY = (27, 38, 86)
BURNT_ORANGE = (241, 91, 34)
MUSTARD = (247, 145, 29)
LIGHT_TEXT = (51, 51, 51)
LIGHT_SEC_BG = (245, 245, 245)

NAVY_HEX = '#1b2656'
ORANGE_HEX = '#f15b22'
MUSTARD_HEX = '#f7911d'


def format_currency(amount):
    return f"R {amount:,.0f}".replace(",", " ")


def calc_years_between(start_date_str, end_date_str):
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    return (end - start).days / 365.25


def adjust_for_tvm(price, rate, years):
    return price * ((1 + (rate / 100)) ** years)


# --- 1. GATHER MACRO & MICRO DATA ---
print("\n--- LARNEY PROPERTIES: VISUAL VALUATION ENGINE ---\n")
client_name = input("Client Surname: ")
address = input("Property Address: ")

inflation_rate = float(input("\nCurrent Annual Inflation Rate (e.g., 5.5): "))
repo_rate = float(input("Current SARB Repo Rate (e.g., 8.25): "))

print("\n[ Subject Property ]")
subject_sold_date = input("Date Last Sold (YYYY-MM-DD): ")
subject_sold_price = float(input("Price Last Sold For: "))

print("\n[ Comparable Property 1 ]")
c1_date = input("Date Sold (YYYY-MM-DD): ")
c1_price = float(input("Price Sold For: "))

print("\n[ Comparable Property 2 ]")
c2_date = input("Date Sold (YYYY-MM-DD): ")
c2_price = float(input("Price Sold For: "))

print("\n[ Comparable Property 3 ]")
c3_date = input("Date Sold (YYYY-MM-DD): ")
c3_price = float(input("Price Sold For: "))

# --- 2. THE QUANTITATIVE MATH ---
date_today = datetime.now().strftime("%Y-%m-%d")

subject_years = calc_years_between(subject_sold_date, date_today)
adj_subject = adjust_for_tvm(subject_sold_price, inflation_rate, subject_years)

c1_years = calc_years_between(c1_date, date_today)
c1_adj = adjust_for_tvm(c1_price, inflation_rate, c1_years)
c2_years = calc_years_between(c2_date, date_today)
c2_adj = adjust_for_tvm(c2_price, inflation_rate, c2_years)
c3_years = calc_years_between(c3_date, date_today)
c3_adj = adjust_for_tvm(c3_price, inflation_rate, c3_years)

average_adj_comps = (c1_adj + c2_adj + c3_adj) / 3
blended_market_value = (adj_subject * 0.4) + (average_adj_comps * 0.6)
estimated_equity = blended_market_value - subject_sold_price

# --- 3. GENERATE THE CHART (Matplotlib) ---
plt.figure(figsize=(7, 4))  # Wide aspect ratio to fit nicely on A4
labels = ['Original Purchase', 'Market Comps (Avg)', 'Blended Valuation']
values = [subject_sold_price, average_adj_comps, blended_market_value]
colors = [NAVY_HEX, MUSTARD_HEX, ORANGE_HEX]

bars = plt.bar(labels, values, color=colors, width=0.6)
plt.title('Property Value Growth Trajectory', color=NAVY_HEX, fontweight='bold', fontsize=14)
plt.ylabel('Value in ZAR', color=LIGHT_TEXT_HEX if 'LIGHT_TEXT_HEX' in locals() else '#333333')
plt.grid(axis='y', linestyle='--', alpha=0.5)

# Add values on top of bars
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width() / 2, yval + (yval * 0.02), f'R{yval / 1000000:.2f}m', ha='center',
             va='bottom', fontweight='bold', color=NAVY_HEX)

# Remove top and right borders for a cleaner look
plt.gca().spines['top'].set_visible(False)
plt.gca().spines['right'].set_visible(False)
plt.tight_layout()

chart_filename = "temp_chart.png"
plt.savefig(chart_filename, dpi=300, transparent=True)
plt.close()


# --- 4. BUILD THE BRANDED PDF ---
class QuantPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 20)
        self.set_text_color(*NAVY)
        self.cell(0, 10, 'LARNEY PROPERTIES', ln=True, align='C')

        self.set_font('Arial', 'I', 11)
        self.set_text_color(*MUSTARD)
        self.cell(0, 6, 'Quantitative Property Valuation & Equity Analysis', ln=True, align='C')

        self.set_draw_color(*BURNT_ORANGE)
        self.set_line_width(1.2)
        self.line(10, 30, 200, 30)
        self.ln(12)

    def footer(self):
        # 1. Move cursor to 25mm from the bottom
        self.set_y(-25)

        # 2. Draw the Navy line ABOVE the text (Y-coordinate 270 instead of 275)
        self.set_draw_color(*NAVY)
        self.set_line_width(0.5)
        self.line(10, 270, 200, 270)

        # 3. Add your updated text below the line
        self.set_font('Arial', '', 10)
        self.set_text_color(150, 150, 150)

        # We use cell height of 10 to give it a little breathing room below the line
        self.cell(0, 10, "Prepared by Jonathan | Let's review these metrics over coffee", ln=True, align='C')


pdf = QuantPDF()
pdf.add_page()
pdf.set_auto_page_break(auto=True, margin=15)


# Helper function for Section Headers
def section_header(title):
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(255, 255, 255)  # White text on Navy
    pdf.cell(0, 10, f"  {title}", ln=True, fill=True)
    pdf.ln(3)


# 1. Subject Property & Macro
section_header('1. BASELINE METRICS & MACRO INDICATORS')
pdf.set_font('Arial', '', 11)
pdf.set_text_color(*LIGHT_TEXT)
pdf.cell(100, 6, f"Property: {address}")
pdf.cell(90, 6, f"Analysis Date: {date_today}", align='R', ln=True)
pdf.cell(100, 6, f"Original Purchase: {subject_sold_date} ({subject_years:.2f} yrs ago)")
pdf.cell(90, 6, f"Inflation: {inflation_rate}% | Repo: {repo_rate}%", align='R', ln=True)
pdf.ln(8)

# 2. Insert the Chart! (Centered)
# Y-position adjustment to fit nicely
current_y = pdf.get_y()
pdf.image(chart_filename, x=25, y=current_y, w=160)
pdf.set_y(current_y + 85)  # Move cursor down past the image
pdf.ln(5)

# 3. Market Triangulation Data
section_header('2. MARKET TRIANGULATION (COMP-ADJUSTED)')
pdf.set_font('Arial', '', 11)
pdf.set_text_color(*LIGHT_TEXT)
pdf.set_fill_color(*LIGHT_SEC_BG)

# Boxed Comp Data
pdf.cell(0, 8, f"  Comp 1: Sold {c1_date} for {format_currency(c1_price)} -> Adjusted: {format_currency(c1_adj)}",
         ln=True, fill=True)
pdf.ln(1)
pdf.cell(0, 8, f"  Comp 2: Sold {c2_date} for {format_currency(c2_price)} -> Adjusted: {format_currency(c2_adj)}",
         ln=True, fill=True)
pdf.ln(1)
pdf.cell(0, 8, f"  Comp 3: Sold {c3_date} for {format_currency(c3_price)} -> Adjusted: {format_currency(c3_adj)}",
         ln=True, fill=True)
pdf.ln(8)

# 4. Final Valuation Output (Large & Centered)
pdf.set_fill_color(*LIGHT_SEC_BG)
pdf.rect(10, pdf.get_y(), 190, 45, 'F')  # Draw a background box for the final numbers
pdf.ln(5)

pdf.set_font('Arial', 'B', 14)
pdf.set_text_color(*NAVY)
pdf.cell(0, 8, 'FINAL CALCULATED MARKET VALUE', ln=True, align='C')

pdf.set_font('Arial', 'B', 22)
pdf.set_text_color(*BURNT_ORANGE)
pdf.cell(0, 12, format_currency(blended_market_value), ln=True, align='C')

pdf.set_font('Arial', 'B', 12)
pdf.set_text_color(*MUSTARD)
pdf.cell(0, 8, f"Estimated Accrued Equity: {format_currency(estimated_equity)}", ln=True, align='C')

# Save and Cleanup
filename = f"Quant_Valuation_{client_name.replace(' ', '_')}.pdf"
pdf.output(filename)
os.remove(chart_filename)  # Delete the temporary chart image
print(f"\n[+] Full-Page Visual PDF Generated Successfully: {filename}")