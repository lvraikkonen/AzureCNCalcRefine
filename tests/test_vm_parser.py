"""Tests for VM productName parser and sub-dimension extraction.

Covers all 240 unique VM productName values from the Azure.cn CSV data.
"""

import csv
from pathlib import Path

import pytest

from app.services.sub_dimensions.vm_parser import VmParsedProduct, parse_vm_product_name
from app.services.sub_dimensions.vm_category_map import get_vm_category, CATEGORY_OVERRIDES
from app.services.sub_dimensions import VmProductNameParser, get_sub_dimension_parser


# ── All 240 productName parametrized tests ─────────────────────────────
# Tuple: (product_name, os, deployment, series, category, tier, memory_profile, special)

ALL_VM_PRODUCTS = [
    ('Basv2 Series Cloud Services', "Linux", "Cloud Services", "Basv2", "General Purpose", None, None, None),
    ('Bsv2 Series Cloud Services', "Linux", "Cloud Services", "Bsv2", "General Purpose", None, None, None),
    ('DCadsv6 Series Dedicated Host', "Linux", "Dedicated Host", "DCadsv6", "General Purpose", None, None, None),
    ('DCasv6 Series Dedicated Host', "Linux", "Dedicated Host", "DCasv6", "General Purpose", None, None, None),
    ('DSv3 Series Dedicated Host', "Linux", "Dedicated Host", "DSv3", "General Purpose", None, None, None),
    ('DSv4 Series Dedicated Host', "Linux", "Dedicated Host", "DSv4", "General Purpose", None, None, None),
    ('Dadsv5 Series Cloud Services', "Linux", "Cloud Services", "Dadsv5", "General Purpose", None, None, None),
    ('Dadsv5 Series Dedicated Host', "Linux", "Dedicated Host", "Dadsv5", "General Purpose", None, None, None),
    ('Dasv4 Series Dedicated Host', "Linux", "Dedicated Host", "Dasv4", "General Purpose", None, None, None),
    ('Dasv5 Series Cloud Services', "Linux", "Cloud Services", "Dasv5", "General Purpose", None, None, None),
    ('Dasv5 Series Dedicated Host', "Linux", "Dedicated Host", "Dasv5", "General Purpose", None, None, None),
    ('Dasv6 Series Dedicated Host', "Linux", "Dedicated Host", "Dasv6", "General Purpose", None, None, None),
    ('Ddsv4 Series Dedicated Host', "Linux", "Dedicated Host", "Ddsv4", "General Purpose", None, None, None),
    ('Ddsv5 Series DedicatedHost', "Linux", "Dedicated Host", "Ddsv5", "General Purpose", None, None, None),
    ('Ddsv6 Series DedicatedHost', "Linux", "Dedicated Host", "Ddsv6", "General Purpose", None, None, None),
    ('Dedicated Host Reservation', "Linux", "Dedicated Host", None, None, None, None, "Reservation"),
    ('Dsv5 Series DedicatedHost', "Linux", "Dedicated Host", "Dsv5", "General Purpose", None, None, None),
    ('Dsv6 Series Dedicated Host', "Linux", "Dedicated Host", "Dsv6", "General Purpose", None, None, None),
    ('ECadsv6 Series Dedicated Host', "Linux", "Dedicated Host", "ECadsv6", "Memory Optimized", None, None, None),
    ('ECasv6 Series Dedicated Host', "Linux", "Dedicated Host", "ECasv6", "Memory Optimized", None, None, None),
    ('ESv3 Series Dedicated Host', "Linux", "Dedicated Host", "ESv3", "Memory Optimized", None, None, None),
    ('ESv4 Series Dedicated Host', "Linux", "Dedicated Host", "ESv4", "Memory Optimized", None, None, None),
    ('Eadsv5 Series CloudServices', "Linux", "Cloud Services", "Eadsv5", "Memory Optimized", None, None, None),
    ('Eadsv5 Series DedicatedHost', "Linux", "Dedicated Host", "Eadsv5", "Memory Optimized", None, None, None),
    ('Easv4 Series Dedicated Host', "Linux", "Dedicated Host", "Easv4", "Memory Optimized", None, None, None),
    ('Easv5 Series CloudServices', "Linux", "Cloud Services", "Easv5", "Memory Optimized", None, None, None),
    ('Easv5 Series DedicatedHost', "Linux", "Dedicated Host", "Easv5", "Memory Optimized", None, None, None),
    ('Easv6 Series Dedicated Host', "Linux", "Dedicated Host", "Easv6", "Memory Optimized", None, None, None),
    ('Ebdsv5 Series Dedicated Host', "Linux", "Dedicated Host", "Ebdsv5", "Memory Optimized", None, None, None),
    ('Ebsv5 Series Dedicated Host', "Linux", "Dedicated Host", "Ebsv5", "Memory Optimized", None, None, None),
    ('Edsv4 Series Dedicated Host', "Linux", "Dedicated Host", "Edsv4", "Memory Optimized", None, None, None),
    ('Edsv5 Series DedicatedHost', "Linux", "Dedicated Host", "Edsv5", "Memory Optimized", None, None, None),
    ('Esv5 Series DedicatedHost', "Linux", "Dedicated Host", "Esv5", "Memory Optimized", None, None, None),
    ('Esv6 Series DedicatedHost', "Linux", "Dedicated Host", "Esv6", "Memory Optimized", None, None, None),
    ('FSv2 Series Dedicated Host', "Linux", "Dedicated Host", "FSv2", "Compute Optimized", None, None, None),
    ('FX Series Dedicated Host', "Linux", "Dedicated Host", "FX", "Compute Optimized", None, None, None),
    ('LSv2 Series Dedicated Host', "Linux", "Dedicated Host", "LSv2", "Storage Optimized", None, None, None),
    ('Lasv3 Series DedicatedHost', "Linux", "Dedicated Host", "Lasv3", "Storage Optimized", None, None, None),
    ('Lasv3 Series Linux', "Linux", "Virtual Machines", "Lasv3", "Storage Optimized", None, None, None),
    ('Lasv3 Series Windows', "Windows", "Virtual Machines", "Lasv3", "Storage Optimized", None, None, None),
    ('Lsv3 Series Dedicated Host', "Linux", "Dedicated Host", "Lsv3", "Storage Optimized", None, None, None),
    ('MS Series Dedicated Host', "Linux", "Dedicated Host", "MS", "Memory Optimized", None, None, None),
    ('MSv2 Series Dedicated Host', "Linux", "Dedicated Host", "MSv2", "Memory Optimized", None, None, None),
    ('MdSv2 Series Dedicated Host', "Linux", "Dedicated Host", "MdSv2", "Memory Optimized", None, None, None),
    ('NCads A100 v4 Series Linux', "Linux", "Virtual Machines", "NCads A100 v4", "GPU", None, None, None),
    ('NCads A100 v4 Series Windows', "Windows", "Virtual Machines", "NCads A100 v4", "GPU", None, None, None),
    ('NVasv4 Series Dedicated Host', "Linux", "Dedicated Host", "NVasv4", "GPU", None, None, None),
    ('Virtual Machines A Series', "Linux", "Virtual Machines", "A", "General Purpose", None, None, None),
    ('Virtual Machines A Series Basic', "Linux", "Virtual Machines", "A", "General Purpose", "Basic", None, None),
    ('Virtual Machines A Series Basic Windows', "Windows", "Virtual Machines", "A", "General Purpose", "Basic", None, None),
    ('Virtual Machines A Series Windows', "Windows", "Virtual Machines", "A", "General Purpose", None, None, None),
    ('Virtual Machines Av2 Series', "Linux", "Virtual Machines", "Av2", "General Purpose", None, None, None),
    ('Virtual Machines Av2 Series Windows', "Windows", "Virtual Machines", "Av2", "General Purpose", None, None, None),
    ('Virtual Machines BS Series', "Linux", "Virtual Machines", "BS", "General Purpose", None, None, None),
    ('Virtual Machines BS Series Windows', "Windows", "Virtual Machines", "BS", "General Purpose", None, None, None),
    ('Virtual Machines Basv2 Series', "Linux", "Virtual Machines", "Basv2", "General Purpose", None, None, None),
    ('Virtual Machines Basv2 Series Windows', "Windows", "Virtual Machines", "Basv2", "General Purpose", None, None, None),
    ('Virtual Machines Bsv2 Series', "Linux", "Virtual Machines", "Bsv2", "General Purpose", None, None, None),
    ('Virtual Machines Bsv2 Series Windows', "Windows", "Virtual Machines", "Bsv2", "General Purpose", None, None, None),
    ('Virtual Machines D Series', "Linux", "Virtual Machines", "D", "General Purpose", None, None, None),
    ('Virtual Machines D Series Windows', "Windows", "Virtual Machines", "D", "General Purpose", None, None, None),
    ('Virtual Machines DCadsv6 series', "Linux", "Virtual Machines", "DCadsv6", "General Purpose", None, None, None),
    ('Virtual Machines DCadsv6 series Windows', "Windows", "Virtual Machines", "DCadsv6", "General Purpose", None, None, None),
    ('Virtual Machines DCasv6 series', "Linux", "Virtual Machines", "DCasv6", "General Purpose", None, None, None),
    ('Virtual Machines DCasv6 series Windows', "Windows", "Virtual Machines", "DCasv6", "General Purpose", None, None, None),
    ('Virtual Machines DS Series', "Linux", "Virtual Machines", "DS", "General Purpose", None, None, None),
    ('Virtual Machines DS Series Windows', "Windows", "Virtual Machines", "DS", "General Purpose", None, None, None),
    ('Virtual Machines DSv2 Series', "Linux", "Virtual Machines", "DSv2", "General Purpose", None, None, None),
    ('Virtual Machines DSv2 Series Windows', "Windows", "Virtual Machines", "DSv2", "General Purpose", None, None, None),
    ('Virtual Machines DSv2 promo Series', "Linux", "Virtual Machines", "DSv2 promo", "General Purpose", None, None, None),
    ('Virtual Machines DSv2 promo Series Windows', "Windows", "Virtual Machines", "DSv2 promo", "General Purpose", None, None, None),
    ('Virtual Machines DSv3 Series', "Linux", "Virtual Machines", "DSv3", "General Purpose", None, None, None),
    ('Virtual Machines DSv3 Series Windows', "Windows", "Virtual Machines", "DSv3", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv5 Series', "Linux", "Virtual Machines", "Dadsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv5 Series Windows', "Windows", "Virtual Machines", "Dadsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv6 Series', "Linux", "Virtual Machines", "Dadsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv6 Series Windows', "Windows", "Virtual Machines", "Dadsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv7 Series', "Linux", "Virtual Machines", "Dadsv7", "General Purpose", None, None, None),
    ('Virtual Machines Dadsv7 Series Windows', "Windows", "Virtual Machines", "Dadsv7", "General Purpose", None, None, None),
    ('Virtual Machines Daldsv6 Series', "Linux", "Virtual Machines", "Daldsv6", "General Purpose", None, None, None),
    ('Virtual Machines Daldsv6 Series Windows', "Windows", "Virtual Machines", "Daldsv6", "General Purpose", None, None, None),
    ('Virtual Machines Daldsv7 Series', "Linux", "Virtual Machines", "Daldsv7", "General Purpose", None, None, None),
    ('Virtual Machines Daldsv7 Series Windows', "Windows", "Virtual Machines", "Daldsv7", "General Purpose", None, None, None),
    ('Virtual Machines Dalsv6 Series', "Linux", "Virtual Machines", "Dalsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dalsv6 Series Windows', "Windows", "Virtual Machines", "Dalsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dalsv7 Series', "Linux", "Virtual Machines", "Dalsv7", "General Purpose", None, None, None),
    ('Virtual Machines Dalsv7 Series Windows', "Windows", "Virtual Machines", "Dalsv7", "General Purpose", None, None, None),
    ('Virtual Machines Dasv4 Series', "Linux", "Virtual Machines", "Dasv4", "General Purpose", None, None, None),
    ('Virtual Machines Dasv4 Series Windows', "Windows", "Virtual Machines", "Dasv4", "General Purpose", None, None, None),
    ('Virtual Machines Dasv5 Series', "Linux", "Virtual Machines", "Dasv5", "General Purpose", None, None, None),
    ('Virtual Machines Dasv5 Series Windows', "Windows", "Virtual Machines", "Dasv5", "General Purpose", None, None, None),
    ('Virtual Machines Dasv6 Series', "Linux", "Virtual Machines", "Dasv6", "General Purpose", None, None, None),
    ('Virtual Machines Dasv6 Series Windows', "Windows", "Virtual Machines", "Dasv6", "General Purpose", None, None, None),
    ('Virtual Machines Dasv7 Series', "Linux", "Virtual Machines", "Dasv7", "General Purpose", None, None, None),
    ('Virtual Machines Dasv7 Series Windows', "Windows", "Virtual Machines", "Dasv7", "General Purpose", None, None, None),
    ('Virtual Machines Dav4 Series', "Linux", "Virtual Machines", "Dav4", "General Purpose", None, None, None),
    ('Virtual Machines Dav4 Series Windows', "Windows", "Virtual Machines", "Dav4", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv4 Series', "Linux", "Virtual Machines", "Ddsv4", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv4 Series Windows', "Windows", "Virtual Machines", "Ddsv4", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv5 Series', "Linux", "Virtual Machines", "Ddsv5", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv5 Series Windows', "Windows", "Virtual Machines", "Ddsv5", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv6 Series', "Linux", "Virtual Machines", "Ddsv6", "General Purpose", None, None, None),
    ('Virtual Machines Ddsv6 Series Windows', "Windows", "Virtual Machines", "Ddsv6", "General Purpose", None, None, None),
    ('Virtual Machines Ddv4 Series', "Linux", "Virtual Machines", "Ddv4", "General Purpose", None, None, None),
    ('Virtual Machines Ddv4 Series Windows', "Windows", "Virtual Machines", "Ddv4", "General Purpose", None, None, None),
    ('Virtual Machines Ddv5 Series', "Linux", "Virtual Machines", "Ddv5", "General Purpose", None, None, None),
    ('Virtual Machines Ddv5 Series Windows', "Windows", "Virtual Machines", "Ddv5", "General Purpose", None, None, None),
    ('Virtual Machines Dldsv5 Series', "Linux", "Virtual Machines", "Dldsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dldsv5 Series Windows', "Windows", "Virtual Machines", "Dldsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dldsv6 Series', "Linux", "Virtual Machines", "Dldsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dldsv6 Series Windows', "Windows", "Virtual Machines", "Dldsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dlsv5 Series', "Linux", "Virtual Machines", "Dlsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dlsv5 Series Windows', "Windows", "Virtual Machines", "Dlsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dlsv6 Series', "Linux", "Virtual Machines", "Dlsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dlsv6 Series Windows', "Windows", "Virtual Machines", "Dlsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dpdsv6 Series', "Linux", "Virtual Machines", "Dpdsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dpldsv6 Series', "Linux", "Virtual Machines", "Dpldsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dplsv6 Series', "Linux", "Virtual Machines", "Dplsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dpsv6 Series', "Linux", "Virtual Machines", "Dpsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dsv4 Series', "Linux", "Virtual Machines", "Dsv4", "General Purpose", None, None, None),
    ('Virtual Machines Dsv4 Series Windows', "Windows", "Virtual Machines", "Dsv4", "General Purpose", None, None, None),
    ('Virtual Machines Dsv5 Series', "Linux", "Virtual Machines", "Dsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dsv5 Series Windows', "Windows", "Virtual Machines", "Dsv5", "General Purpose", None, None, None),
    ('Virtual Machines Dsv6 Series', "Linux", "Virtual Machines", "Dsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dsv6 Series Windows', "Windows", "Virtual Machines", "Dsv6", "General Purpose", None, None, None),
    ('Virtual Machines Dv2 Series', "Linux", "Virtual Machines", "Dv2", "General Purpose", None, None, None),
    ('Virtual Machines Dv2 Series Windows', "Windows", "Virtual Machines", "Dv2", "General Purpose", None, None, None),
    ('Virtual Machines Dv2 promo Series', "Linux", "Virtual Machines", "Dv2 promo", "General Purpose", None, None, None),
    ('Virtual Machines Dv2 promo Series Windows', "Windows", "Virtual Machines", "Dv2 promo", "General Purpose", None, None, None),
    ('Virtual Machines Dv3 Series', "Linux", "Virtual Machines", "Dv3", "General Purpose", None, None, None),
    ('Virtual Machines Dv3 Series Windows', "Windows", "Virtual Machines", "Dv3", "General Purpose", None, None, None),
    ('Virtual Machines Dv4 Series', "Linux", "Virtual Machines", "Dv4", "General Purpose", None, None, None),
    ('Virtual Machines Dv4 Series Windows', "Windows", "Virtual Machines", "Dv4", "General Purpose", None, None, None),
    ('Virtual Machines Dv5 Series', "Linux", "Virtual Machines", "Dv5", "General Purpose", None, None, None),
    ('Virtual Machines Dv5 Series Windows', "Windows", "Virtual Machines", "Dv5", "General Purpose", None, None, None),
    ('Virtual Machines ECadsv6 series Linux', "Linux", "Virtual Machines", "ECadsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines ECadsv6 series Windows', "Windows", "Virtual Machines", "ECadsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines ECasv6 series', "Linux", "Virtual Machines", "ECasv6", "Memory Optimized", None, None, None),
    ('Virtual Machines ECasv6 series Windows', "Windows", "Virtual Machines", "ECasv6", "Memory Optimized", None, None, None),
    ('Virtual Machines ESv3 Series', "Linux", "Virtual Machines", "ESv3", "Memory Optimized", None, None, None),
    ('Virtual Machines ESv3 Series Windows', "Windows", "Virtual Machines", "ESv3", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv5 Series', "Linux", "Virtual Machines", "Eadsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv5 Series Windows', "Windows", "Virtual Machines", "Eadsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv6 Series', "Linux", "Virtual Machines", "Eadsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv6 Series Windows', "Windows", "Virtual Machines", "Eadsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv7 Series', "Linux", "Virtual Machines", "Eadsv7", "Memory Optimized", None, None, None),
    ('Virtual Machines Eadsv7 Series Windows', "Windows", "Virtual Machines", "Eadsv7", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv4 Series', "Linux", "Virtual Machines", "Easv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv4 Series Windows', "Windows", "Virtual Machines", "Easv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv5 Series', "Linux", "Virtual Machines", "Easv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv5 Series Windows', "Windows", "Virtual Machines", "Easv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv6 Series', "Linux", "Virtual Machines", "Easv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv6 Series Windows', "Windows", "Virtual Machines", "Easv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv7 Series', "Linux", "Virtual Machines", "Easv7", "Memory Optimized", None, None, None),
    ('Virtual Machines Easv7 Series Windows', "Windows", "Virtual Machines", "Easv7", "Memory Optimized", None, None, None),
    ('Virtual Machines Eav4 Series', "Linux", "Virtual Machines", "Eav4", "Memory Optimized", None, None, None),
    ('Virtual Machines Eav4 Series Windows', "Windows", "Virtual Machines", "Eav4", "Memory Optimized", None, None, None),
    ('Virtual Machines Ebdsv5 Series', "Linux", "Virtual Machines", "Ebdsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Ebdsv5 Series Windows', "Windows", "Virtual Machines", "Ebdsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Ebsv5 Series', "Linux", "Virtual Machines", "Ebsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Ebsv5 Series Windows', "Windows", "Virtual Machines", "Ebsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv4 Series', "Linux", "Virtual Machines", "Edsv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv4 Series Windows', "Windows", "Virtual Machines", "Edsv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv5 Series', "Linux", "Virtual Machines", "Edsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv5 Series Windows', "Windows", "Virtual Machines", "Edsv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv6 Series', "Linux", "Virtual Machines", "Edsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Edsv6 Series Windows', "Windows", "Virtual Machines", "Edsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Edv4 Series', "Linux", "Virtual Machines", "Edv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Edv4 Series Windows', "Windows", "Virtual Machines", "Edv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Edv5 Series', "Linux", "Virtual Machines", "Edv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Edv5 Series Windows', "Windows", "Virtual Machines", "Edv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Epdsv6 Series', "Linux", "Virtual Machines", "Epdsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Epsv6 Series', "Linux", "Virtual Machines", "Epsv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv4 Series', "Linux", "Virtual Machines", "Esv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv4 Series Windows', "Windows", "Virtual Machines", "Esv4", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv5 Series', "Linux", "Virtual Machines", "Esv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv5 Series Windows', "Windows", "Virtual Machines", "Esv5", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv6 Series', "Linux", "Virtual Machines", "Esv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Esv6 Series Windows', "Windows", "Virtual Machines", "Esv6", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev3 Series', "Linux", "Virtual Machines", "Ev3", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev3 Series Windows', "Windows", "Virtual Machines", "Ev3", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev4 Series', "Linux", "Virtual Machines", "Ev4", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev4 Series Windows', "Windows", "Virtual Machines", "Ev4", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev5 Series', "Linux", "Virtual Machines", "Ev5", "Memory Optimized", None, None, None),
    ('Virtual Machines Ev5 Series Windows', "Windows", "Virtual Machines", "Ev5", "Memory Optimized", None, None, None),
    ('Virtual Machines F Series', "Linux", "Virtual Machines", "F", "Compute Optimized", None, None, None),
    ('Virtual Machines F Series Windows', "Windows", "Virtual Machines", "F", "Compute Optimized", None, None, None),
    ('Virtual Machines FS Series', "Linux", "Virtual Machines", "FS", "Compute Optimized", None, None, None),
    ('Virtual Machines FS Series Windows', "Windows", "Virtual Machines", "FS", "Compute Optimized", None, None, None),
    ('Virtual Machines FSv2 Series', "Linux", "Virtual Machines", "FSv2", "Compute Optimized", None, None, None),
    ('Virtual Machines FSv2 Series Windows', "Windows", "Virtual Machines", "FSv2", "Compute Optimized", None, None, None),
    ('Virtual Machines FX Series', "Linux", "Virtual Machines", "FX", "Compute Optimized", None, None, None),
    ('Virtual Machines FX Series Windows', "Windows", "Virtual Machines", "FX", "Compute Optimized", None, None, None),
    ('Virtual Machines Fadsv7 Series', "Linux", "Virtual Machines", "Fadsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Fadsv7 Series Windows', "Windows", "Virtual Machines", "Fadsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Faldsv7 Series', "Linux", "Virtual Machines", "Faldsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Faldsv7 Series Windows', "Windows", "Virtual Machines", "Faldsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Falsv6 Series', "Linux", "Virtual Machines", "Falsv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Falsv6 Series Windows', "Windows", "Virtual Machines", "Falsv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Falsv7 Series', "Linux", "Virtual Machines", "Falsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Falsv7 Series Windows', "Windows", "Virtual Machines", "Falsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Famdsv7 Series', "Linux", "Virtual Machines", "Famdsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Famdsv7 Series Windows', "Windows", "Virtual Machines", "Famdsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Famsv6 Series', "Linux", "Virtual Machines", "Famsv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Famsv6 Series Windows', "Windows", "Virtual Machines", "Famsv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Famsv7 Series', "Linux", "Virtual Machines", "Famsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Famsv7 Series Windows', "Windows", "Virtual Machines", "Famsv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Fasv6 Series', "Linux", "Virtual Machines", "Fasv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Fasv6 Series Windows', "Windows", "Virtual Machines", "Fasv6", "Compute Optimized", None, None, None),
    ('Virtual Machines Fasv7 Series', "Linux", "Virtual Machines", "Fasv7", "Compute Optimized", None, None, None),
    ('Virtual Machines Fasv7 Series Windows', "Windows", "Virtual Machines", "Fasv7", "Compute Optimized", None, None, None),
    ('Virtual Machines HBrsv3 Series', "Linux", "Virtual Machines", "HBrsv3", "High Performance Compute", None, None, None),
    ('Virtual Machines HBrsv3 Series Windows', "Windows", "Virtual Machines", "HBrsv3", "High Performance Compute", None, None, None),
    ('Virtual Machines Lsv3 Series', "Linux", "Virtual Machines", "Lsv3", "Storage Optimized", None, None, None),
    ('Virtual Machines Lsv3 Series Windows', "Windows", "Virtual Machines", "Lsv3", "Storage Optimized", None, None, None),
    ('Virtual Machines Lsv4 Series', "Linux", "Virtual Machines", "Lsv4", "Storage Optimized", None, None, None),
    ('Virtual Machines Lsv4 Series Windows', "Windows", "Virtual Machines", "Lsv4", "Storage Optimized", None, None, None),
    ('Virtual Machines MS Series', "Linux", "Virtual Machines", "MS", "Memory Optimized", None, None, None),
    ('Virtual Machines MS Series Windows', "Windows", "Virtual Machines", "MS", "Memory Optimized", None, None, None),
    ('Virtual Machines MSv2 Series', "Linux", "Virtual Machines", "MSv2", "Memory Optimized", None, None, None),
    ('Virtual Machines MSv2 Series Windows', "Windows", "Virtual Machines", "MSv2", "Memory Optimized", None, None, None),
    ('Virtual Machines Mbdsv3 Series', "Linux", "Virtual Machines", "Mbdsv3", "Memory Optimized", None, None, None),
    ('Virtual Machines Mbdsv3 Series Windows', "Windows", "Virtual Machines", "Mbdsv3", "Memory Optimized", None, None, None),
    ('Virtual Machines Mbsv3 Series', "Linux", "Virtual Machines", "Mbsv3", "Memory Optimized", None, None, None),
    ('Virtual Machines Mbsv3 Series Windows', "Windows", "Virtual Machines", "Mbsv3", "Memory Optimized", None, None, None),
    ('Virtual Machines MdSv2 Series', "Linux", "Virtual Machines", "MdSv2", "Memory Optimized", None, None, None),
    ('Virtual Machines MdSv2 Series Windows', "Windows", "Virtual Machines", "MdSv2", "Memory Optimized", None, None, None),
    ('Virtual Machines Mdsv3 Medium Memory Series Linux', "Linux", "Virtual Machines", "Mdsv3", "Memory Optimized", None, "Medium Memory", None),
    ('Virtual Machines Mdsv3 Medium Memory Series Windows', "Windows", "Virtual Machines", "Mdsv3", "Memory Optimized", None, "Medium Memory", None),
    ('Virtual Machines Msv3 Medium Memory Series Linux', "Linux", "Virtual Machines", "Msv3", "Memory Optimized", None, "Medium Memory", None),
    ('Virtual Machines Msv3 Medium Memory Series Windows', "Windows", "Virtual Machines", "Msv3", "Memory Optimized", None, "Medium Memory", None),
    ('Virtual Machines NCSv3 Series', "Linux", "Virtual Machines", "NCSv3", "GPU", None, None, None),
    ('Virtual Machines NCSv3 Series Windows', "Windows", "Virtual Machines", "NCSv3", "GPU", None, None, None),
    ('Virtual Machines NCasT4 v3 Series', "Linux", "Virtual Machines", "NCasT4 v3", "GPU", None, None, None),
    ('Virtual Machines NCasT4 v3 Series Windows', "Windows", "Virtual Machines", "NCasT4 v3", "GPU", None, None, None),
    ('Virtual Machines NVadsA10v5 Series', "Linux", "Virtual Machines", "NVadsA10v5", "GPU", None, None, None),
    ('Virtual Machines NVadsA10v5 Series Windows', "Windows", "Virtual Machines", "NVadsA10v5", "GPU", None, None, None),
    ('Virtual Machines NVasv4 Series', "Linux", "Virtual Machines", "NVasv4", "GPU", None, None, None),
    ('Virtual Machines NVasv4 Series Windows', "Windows", "Virtual Machines", "NVasv4", "GPU", None, None, None),
    ('Virtual Machines RI', "Linux", "Virtual Machines", None, None, None, None, "RI"),
]


@pytest.mark.parametrize(
    "name,expected_os,expected_deployment,expected_series,expected_category,expected_tier,expected_memory,expected_special",
    ALL_VM_PRODUCTS,
    ids=[t[0] for t in ALL_VM_PRODUCTS],
)
def test_parse_vm_product_name(
    name, expected_os, expected_deployment, expected_series,
    expected_category, expected_tier, expected_memory, expected_special,
):
    result = parse_vm_product_name(name)
    assert result.original == name
    assert result.os == expected_os, f"os: got {result.os!r}"
    assert result.deployment == expected_deployment, f"deployment: got {result.deployment!r}"
    assert result.series == expected_series, f"series: got {result.series!r}"
    assert result.category == expected_category, f"category: got {result.category!r}"
    assert result.tier == expected_tier, f"tier: got {result.tier!r}"
    assert result.memory_profile == expected_memory, f"memory_profile: got {result.memory_profile!r}"
    assert result.special == expected_special, f"special: got {result.special!r}"


# ── Verify against actual CSV data ─────────────────────────────────────

CSV_PATH = Path(__file__).parent.parent / "sample-data" / "AzureRetailPrices.csv"


@pytest.mark.skipif(not CSV_PATH.exists(), reason="CSV data not available")
def test_all_csv_products_parse_without_error():
    """Every VM productName in the CSV should parse without raising."""
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        names = {row["productName"] for row in reader if row["serviceName"] == "Virtual Machines"}

    assert len(names) == 240, f"Expected 240 unique VM products, got {len(names)}"

    for name in sorted(names):
        result = parse_vm_product_name(name)
        assert result.original == name
        # Non-special products must have a series and category
        if result.special is None:
            assert result.series is not None, f"No series for {name!r}"
            assert result.category is not None, f"No category for {name!r}"


@pytest.mark.skipif(not CSV_PATH.exists(), reason="CSV data not available")
def test_csv_coverage():
    """The parametrized test list covers all CSV entries."""
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        csv_names = {row["productName"] for row in reader if row["serviceName"] == "Virtual Machines"}

    test_names = {t[0] for t in ALL_VM_PRODUCTS}
    missing = csv_names - test_names
    assert not missing, f"Missing from test list: {missing}"
    extra = test_names - csv_names
    assert not extra, f"Extra in test list (not in CSV): {extra}"


# ── Category mapping tests ─────────────────────────────────────────────

@pytest.mark.parametrize("series,expected", [
    ("A", "General Purpose"),
    ("Av2", "General Purpose"),
    ("B", "General Purpose"),
    ("BS", "General Purpose"),
    ("D", "General Purpose"),
    ("Dv3", "General Purpose"),
    ("DSv2", "General Purpose"),
    ("DCadsv6", "General Purpose"),
    ("DCasv6", "General Purpose"),
    ("E", "Memory Optimized"),
    ("Ev3", "Memory Optimized"),
    ("ESv3", "Memory Optimized"),
    ("ECadsv6", "Memory Optimized"),
    ("ECasv6", "Memory Optimized"),
    ("F", "Compute Optimized"),
    ("FS", "Compute Optimized"),
    ("FSv2", "Compute Optimized"),
    ("FX", "Compute Optimized"),
    ("H", "High Performance Compute"),
    ("HBrsv3", "High Performance Compute"),
    ("L", "Storage Optimized"),
    ("Lsv3", "Storage Optimized"),
    ("Lasv3", "Storage Optimized"),
    ("LSv2", "Storage Optimized"),
    ("M", "Memory Optimized"),
    ("MS", "Memory Optimized"),
    ("MSv2", "Memory Optimized"),
    ("MdSv2", "Memory Optimized"),
    ("Mdsv3", "Memory Optimized"),
    ("N", "GPU"),
    ("NCSv3", "GPU"),
    ("NCasT4 v3", "GPU"),
    ("NCads A100 v4", "GPU"),
    ("NVadsA10v5", "GPU"),
    ("NVasv4", "GPU"),
])
def test_vm_category(series, expected):
    assert get_vm_category(series) == expected


def test_vm_category_empty():
    assert get_vm_category("") == "Other"
    assert get_vm_category(None) == "Other"


def test_vm_category_unknown():
    assert get_vm_category("Xsomething") == "Other"


# ── Special product exclusion tests ────────────────────────────────────

def test_special_products_excluded():
    """Special products (RI, Reservation) must be flagged."""
    ri = parse_vm_product_name("Virtual Machines RI")
    assert ri.special == "RI"
    assert ri.series is None

    reservation = parse_vm_product_name("Dedicated Host Reservation")
    assert reservation.special == "Reservation"
    assert reservation.deployment == "Dedicated Host"
    assert reservation.series is None


# ── Sub-dimension cascade tests ────────────────────────────────────────

def test_sub_dimension_parser_registered():
    parser = get_sub_dimension_parser("Virtual Machines")
    assert parser is not None
    assert parser.target_field() == "product_name"


def test_sub_dimension_parser_not_registered():
    assert get_sub_dimension_parser("Storage") is None
    assert get_sub_dimension_parser("Nonexistent") is None


def test_extract_sub_dimensions_no_selections():
    """Without sub-selections, all sub-dimension options are returned."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",
        "Virtual Machines Dv3 Series Windows",
        "Virtual Machines Ev3 Series",
        "Virtual Machines FSv2 Series",
        "Virtual Machines NCSv3 Series",
        "Virtual Machines RI",  # should be excluded
    ]

    sub_dims = parser.extract_sub_dimensions(options)

    # Should have 5 sub-dimensions: os, deployment, tier, category, instance_series
    assert len(sub_dims) == 5

    os_dim = next(sd for sd in sub_dims if sd.field == "os")
    os_values = [o.value for o in os_dim.options]
    assert "Linux" in os_values
    assert "Windows" in os_values

    tier_dim = next(sd for sd in sub_dims if sd.field == "tier")
    tier_values = [o.value for o in tier_dim.options]
    assert tier_values == ["Standard"]  # no Basic products in this set

    category_dim = next(sd for sd in sub_dims if sd.field == "category")
    cat_values = [o.value for o in category_dim.options]
    assert "General Purpose" in cat_values
    assert "Memory Optimized" in cat_values
    assert "Compute Optimized" in cat_values
    assert "GPU" in cat_values


def test_extract_sub_dimensions_os_filter():
    """Selecting os=Linux should narrow series to only Linux products."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",          # Linux
        "Virtual Machines Dv3 Series Windows",   # Windows
        "Virtual Machines Ev3 Series",           # Linux
        "Virtual Machines Ev3 Series Windows",   # Windows
        "Virtual Machines NCSv3 Series",         # Linux only
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"os": "Linux"},
    )

    os_dim = next(sd for sd in sub_dims if sd.field == "os")
    assert os_dim.selected == "Linux"
    # OS options should still show both (filtered by OTHER sub-dims, not self)
    assert len(os_dim.options) == 2

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert "Dv3" in series_values
    assert "Ev3" in series_values
    assert "NCSv3" in series_values  # Linux-only product
    assert len(series_values) == 3


def test_extract_sub_dimensions_category_filter():
    """Selecting category=GPU should narrow series to GPU series only."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",
        "Virtual Machines Dv3 Series Windows",
        "Virtual Machines NCSv3 Series",
        "Virtual Machines NCSv3 Series Windows",
        "Virtual Machines NVasv4 Series",
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"category": "GPU"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert "NCSv3" in series_values
    assert "NVasv4" in series_values
    assert "Dv3" not in series_values

    # OS should be narrowed to what's available for GPU
    os_dim = next(sd for sd in sub_dims if sd.field == "os")
    os_values = [o.value for o in os_dim.options]
    assert "Linux" in os_values
    assert "Windows" in os_values  # NCSv3 has Windows variant


def test_extract_sub_dimensions_multi_filter():
    """Multiple sub-selections should cross-filter correctly."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",          # Linux, GP
        "Virtual Machines Dv3 Series Windows",   # Windows, GP
        "Virtual Machines Ev3 Series",           # Linux, MemOpt
        "Virtual Machines Ev3 Series Windows",   # Windows, MemOpt
        "Virtual Machines NCSv3 Series",         # Linux, GPU
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"os": "Linux", "category": "General Purpose"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert series_values == ["Dv3"]  # Only Linux + General Purpose

    # Category options should be filtered by os=Linux only
    category_dim = next(sd for sd in sub_dims if sd.field == "category")
    cat_values = [o.value for o in category_dim.options]
    assert "General Purpose" in cat_values
    assert "Memory Optimized" in cat_values
    assert "GPU" in cat_values  # NCSv3 is Linux GPU


def test_extract_sub_dimensions_deployment_filter():
    """Selecting deployment filters correctly."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",
        "DSv3 Series Dedicated Host",
        "Dadsv5 Series Cloud Services",
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"deployment": "Dedicated Host"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert series_values == ["DSv3"]


def test_special_products_excluded_from_sub_dimensions():
    """RI and Reservation products should not appear in sub-dimension options."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",
        "Virtual Machines RI",
        "Dedicated Host Reservation",
    ]

    sub_dims = parser.extract_sub_dimensions(options)

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert series_values == ["Dv3"]

    deployment_dim = next(sd for sd in sub_dims if sd.field == "deployment")
    deployment_values = [o.value for o in deployment_dim.options]
    assert "Virtual Machines" in deployment_values
    # Dedicated Host Reservation is excluded, so no Dedicated Host
    assert "Dedicated Host" not in deployment_values


# ── Edge case tests ────────────────────────────────────────────────────

def test_lowercase_series_keyword():
    result = parse_vm_product_name("Virtual Machines DCadsv6 series")
    assert result.series == "DCadsv6"
    assert result.os == "Linux"


def test_no_vm_prefix_with_linux_suffix():
    result = parse_vm_product_name("Lasv3 Series Linux")
    assert result.series == "Lasv3"
    assert result.os == "Linux"
    assert result.deployment == "Virtual Machines"


def test_no_vm_prefix_dedicated_host():
    result = parse_vm_product_name("DSv3 Series Dedicated Host")
    assert result.series == "DSv3"
    assert result.deployment == "Dedicated Host"


def test_no_space_dedicated_host():
    result = parse_vm_product_name("Ddsv5 Series DedicatedHost")
    assert result.series == "Ddsv5"
    assert result.deployment == "Dedicated Host"


def test_no_space_cloud_services():
    result = parse_vm_product_name("Eadsv5 Series CloudServices")
    assert result.series == "Eadsv5"
    assert result.deployment == "Cloud Services"


def test_basic_qualifier():
    result = parse_vm_product_name("Virtual Machines A Series Basic")
    assert result.series == "A"
    assert result.tier == "Basic"
    assert result.os == "Linux"


def test_basic_qualifier_windows():
    result = parse_vm_product_name("Virtual Machines A Series Basic Windows")
    assert result.series == "A"
    assert result.tier == "Basic"
    assert result.os == "Windows"


def test_medium_memory_qualifier():
    result = parse_vm_product_name("Virtual Machines Mdsv3 Medium Memory Series Linux")
    assert result.series == "Mdsv3"
    assert result.memory_profile == "Medium Memory"
    assert result.os == "Linux"
    assert result.category == "Memory Optimized"


def test_promo_in_series_name():
    result = parse_vm_product_name("Virtual Machines DSv2 promo Series")
    assert result.series == "DSv2 promo"
    assert result.category == "General Purpose"
    assert result.os == "Linux"


def test_multi_word_series():
    result = parse_vm_product_name("NCads A100 v4 Series Linux")
    assert result.series == "NCads A100 v4"
    assert result.category == "GPU"
    assert result.os == "Linux"
    assert result.deployment == "Virtual Machines"


def test_frozen_dataclass():
    """VmParsedProduct should be immutable."""
    result = parse_vm_product_name("Virtual Machines Dv3 Series")
    with pytest.raises(AttributeError):
        result.os = "Windows"


# ── Tier sub-dimension tests ──────────────────────────────────────────

def test_tier_normalize_none_to_standard():
    """VmProductNameParser.normalize_value maps tier=None → 'Standard'."""
    parser = VmProductNameParser()
    assert parser.normalize_value("tier", None) == "Standard"
    assert parser.normalize_value("tier", "Basic") == "Basic"


def test_tier_normalize_other_fields_unchanged():
    """normalize_value for non-tier fields passes through normally."""
    parser = VmProductNameParser()
    assert parser.normalize_value("os", "Linux") == "Linux"
    assert parser.normalize_value("os", None) is None
    assert parser.normalize_value("category", "GPU") == "GPU"


def test_tier_sub_dimension_options():
    """Tier sub-dimension shows both Standard and Basic when data includes both."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",              # tier=None → Standard
        "Virtual Machines A Series Basic",           # tier=Basic
        "Virtual Machines A Series Basic Windows",   # tier=Basic
        "Virtual Machines Ev3 Series",               # tier=None → Standard
    ]

    sub_dims = parser.extract_sub_dimensions(options)
    tier_dim = next(sd for sd in sub_dims if sd.field == "tier")
    tier_values = [o.value for o in tier_dim.options]
    assert sorted(tier_values) == ["Basic", "Standard"]


def test_tier_sub_dimension_standard_only():
    """When no Basic products exist, tier only shows Standard."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",
        "Virtual Machines Ev3 Series",
    ]

    sub_dims = parser.extract_sub_dimensions(options)
    tier_dim = next(sd for sd in sub_dims if sd.field == "tier")
    assert [o.value for o in tier_dim.options] == ["Standard"]


def test_tier_filter_basic():
    """Selecting tier=Basic narrows to Basic products only."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",              # Standard
        "Virtual Machines A Series Basic",           # Basic
        "Virtual Machines A Series Basic Windows",   # Basic
        "Virtual Machines NCSv3 Series",             # Standard
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"tier": "Basic"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert series_values == ["A"]  # Only A Series has Basic tier

    os_dim = next(sd for sd in sub_dims if sd.field == "os")
    os_values = [o.value for o in os_dim.options]
    assert "Linux" in os_values
    assert "Windows" in os_values


def test_tier_filter_standard():
    """Selecting tier=Standard narrows to non-Basic products."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines Dv3 Series",              # Standard
        "Virtual Machines A Series Basic",           # Basic
        "Virtual Machines NCSv3 Series",             # Standard
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"tier": "Standard"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert "Dv3" in series_values
    assert "NCSv3" in series_values
    assert "A" not in series_values  # A Series Basic is excluded


def test_tier_cross_filter_with_category():
    """Tier + category cross-filter correctly."""
    parser = VmProductNameParser()
    options = [
        "Virtual Machines A Series",                 # GP, Standard
        "Virtual Machines A Series Basic",           # GP, Basic
        "Virtual Machines Dv3 Series",               # GP, Standard
        "Virtual Machines NCSv3 Series",             # GPU, Standard
    ]

    sub_dims = parser.extract_sub_dimensions(
        options,
        current_sub_selections={"tier": "Standard", "category": "General Purpose"},
    )

    series_dim = next(sd for sd in sub_dims if sd.field == "instance_series")
    series_values = [o.value for o in series_dim.options]
    assert sorted(series_values) == ["A", "Dv3"]  # Standard + GP only
