from pipeline.normalize import clean, clean_npi, person, specialty, split_full_name


def test_clean_strips_accents_case_and_punctuation():
    assert clean("  José-María O'Neil ") == "JOSE MARIA ONEIL"


def test_person_drops_titles_and_suffixes():
    assert person("Dr. John", "", "Smith Jr., M.D.") == {"first": "JOHN", "middle": "", "last": "SMITH"}


def test_person_moves_extra_first_tokens_to_middle():
    assert person("John A.", "", "Smith")["middle"] == "A"


def test_split_full_name_both_orders():
    assert split_full_name("Smith, John A") == ("JOHN", "A", "SMITH")
    assert split_full_name("Dr John A Smith MD") == ("JOHN", "A", "SMITH")


def test_npi_requires_ten_digits():
    assert clean_npi("1234567890") == "1234567890"
    assert clean_npi("0") == "" and clean_npi("0000000000") == "" and clean_npi("123") == ""


def test_specialty_maps_leie_and_candidate_vocabulary():
    assert specialty("GENERAL PRACTICE/FP") == specialty("Family Medicine") == "FAMILY_MEDICINE"
    assert specialty("GYN/OBS") == "OBGYN"
    assert specialty("") == ""
