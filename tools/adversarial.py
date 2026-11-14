"""Hand-written requests in wording not used by dev.jsonl; prints the parser's reading."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agentx.parser import Parser
P = Parser()
CASES = [
    "I want a pair of Pacevo running shoes in black, UK size 9, nothing above 4000",
    "Kudova sneakers, white, size eleven, price limit 7000",
    "got any Strydo flip flops in navy size 8 for less than a thousand",
    "searching for a grey Urbanyx hoodie, medium, budget around fifteen hundred",
    "red Pacevo tee, extra small, max 700 bucks",
    "Northweft jeans waist thirty two black under 2.5 thousand",
    "mujhe safed Mehrin kurta chahiye, size S, hazaar rupaye tak",
    "Tanaro dress in pink XL no wait L, under Rs 3,000",
    "blue Wavlo headphones under 7k please",
    "Zentrail jacket, olive, size M, max three thousand seven hundred",
    "I'd love some Loomsy sneakers in navy, size 7, ideally under 4500",
    "dikhao Urbanyx ka kaala hoodie XL do hazaar tak",
    "grey track pants by Pacevo size L under 1500 actually make it XL",
    "a Carrafel wallet in tan please, under 1000",
    "Pacevo cap white below 400 sorry, beige",
    "running shoes size 10, blue, Pacevo, 4k max",
    "sneakers from Loomsy in green size 8 sorry 9",
    "Audora white headset 800 tak",
    "Horavo watch blue 2300 se kam",
    "Urbanyx slides black size 7 UK seven hundred rupees max",
]
for c in CASES:
    print(P.parse(c.split()).filters, " <=", c)
