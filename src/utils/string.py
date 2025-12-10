import re
import html


def camel_to_snake(name: str):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)  # Split before the last uppercase letter followed by lowercase ones (oABCdeF -> oAB_CdeF)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)  # Process corners (oAB_CdeF -> o_AB_Cde_F)
    return s2.lower()
