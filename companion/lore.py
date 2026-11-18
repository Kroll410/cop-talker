"""Who's who of the S.T.A.L.K.E.R. series, as a stalker on Затон would know it in 2012 (Call of Pripyat: after
Стрілець switched off Випалювач мізків). When someone names one of them, the NPC gets these facts so his
answer fits the games instead of being made up.

Facts come from the games' own texts (CoP's Ukrainian localisation: Стрілець, «Долг», «Воля") and the well-known
story of Shadow of Chernobyl and Clear Sky. Names that are also ordinary words (Привид, Клик, Ной, Сич, Кардан)
only count with a capital letter.
"""
import re

STRELOK = (
    "Стрілець (Strelok), also called Мічений (Marked One): the most famous stalker. He once came out of a 'death "
    "truck' with no memory and a tattoo; trader Сидорович on Кордон took him in. With his friends Привид and Клик "
    "he got through Випалювач мізків to the ЧАЕС; after that they split up, he was wounded and stayed "
    "with Доктор on the Болота; mercenaries later killed Клик. In 2012 he switched off Випалювач мізків at the "
    "Radar, which is why the north (Затон, Янів, Прип'ять) is open now. What he found at the ЧАЕС nobody knows for "
    "sure. Rumour has it he's back in the Zone looking for his old friends' stashes and has been seen heading to "
    "Прип'ять. Мічений and Стрілець are the same man, though some still argue.")

# (pattern, case_sensitive, facts)
LORE = [
    (r"\bстріл(ець|ьця|ьцю|ьцем|ьцеві)\b|\bstrelok\b|мічен(ий|ого|ому|им)\b|мечен(ый|ого|ому|ым|ий)\b|"
     r"marked one", False, STRELOK),
    # "Стрілок/Стрілка", "Стрелок" only with a capital: lowercase they are arrows, clock hands and shooters
    (r"\bСтріл(ок|ка|ку|ком|кові)\b|\bСтрел(ок|ка|ку|ком)\b", True, STRELOK),
    (r"сидорович\w*|\bсидор(а|у|ом)?\b", False,
     "Сидорович: a fat, greedy trader who sits in a basement bunker in the rookie village on Кордон, at the southern "
     "edge of the Zone. Buys anything, sells at robbery prices, never leaves his bunker; half the veterans started by "
     "working off a debt to him. He has decent tools."),
    (r"бармен\w*|barman", False,
     "Бармен: owner of the bar «100 рентген» at Росток, neutral ground guarded by «Долг»; gives jobs, buys info, pours "
     "vodka. Everyone who went north passed through his bar."),
    (r"воронін\w*|воронин\w*", False,
     "Генерал Воронін: leader of «Долг» (Обов'язок), headquarters at the Росток factory. Stern, values discipline; "
     "awards the order «Сєрєбряний щіт»."),
    (r"таченк\w*", False,
     "Генерал Таченко: legendary founder of «Долг». Recently a PDA turned up showing he abandoned his men, broke their "
     "radio and died in a space bubble; «Воля» spreads it with glee."),
    (r"лукаш\w*", False,
     "Лукаш: leader of «Воля» (Свобода) at the Army warehouses (Армійські склади), sworn enemy of «Долг». On Янів "
     "«Воля» answers to Локі."),
    (r"сахаров\w*", False,
     "Професор Сахаров: scientist with a lab bunker at Янтар; invented the psi-protection helmet; pays well for "
     "artifacts and measurements."),
    (r"\bшрам\w*|\bscar\b", False,
     "Шрам (Scar): a mercenary and guide for «Чисте небо» in 2011, the man who tried to stop Стрілець at the Brain "
     "Scorcher. What became of him nobody knows for sure; most think the Zone took him."),
    (r"лебед[єе]в\w*", False,
     "Лебедєв: leader of «Чисте небо» (Clear Sky), the scientists-turned-fighters from the Болота who tried to stop "
     "the Zone from growing. After their push to the ЧАЕС in 2011 the group was nearly wiped out; nothing heard of "
     "him since."),
    (r"Привид\w*|Призрак\w*", True,
     "Привид (Ghost): one of Стрілець's group who went through Випалювач мізків with him. Hasn't been seen since; "
     "his notes turn up in old stashes."),
    (r"Клик\w*", True,
     "Клик (Fang): Стрілець's friend from his group; killed by mercenaries after they came back from the ЧАЕС."),
    (r"Доктор\w*", True,
     "Доктор: a legendary healer who lives somewhere on the Болота; patched up Стрілець. Hardly anyone has met him."),
    (r"камінь бажань|виконавець бажань|виконувач бажань|исполнитель желаний|wish granter|\bмонолітові\b", False,
     "The Wish Granter (Виконувач бажань): a legend of a stone at the heart of the ЧАЕС that grants any wish. "
     "«Моноліт» worships it. Those who went for it came back mad or never came back."),
    (r"випалювач\w*|выжигател\w*|brain scorcher", False,
     "Випалювач мізків: a psi-installation at the Radar that burned the minds of anyone heading "
     "north, making them zombies. Switched off in 2012 (they say by Стрілець); that opened the way north, and the "
     "scientists' bunker on Янів was dropped there right after."),
    (r"Кардан\w*", True,
     "Кардан: technician at the «Скадовськ», a hand of gold when sober, but he has nearly drunk himself to death out "
     "of grief: his close friends disappeared. Does upgrades if he has the tools."),
    (r"\bСич\b|\bСича\b|\bСичу\b|\bСичем\b|\bСичеві\b|\bСыч\w*", True,
     "Сич: trader on the «Скадовськ»; buys information above all, knows everyone's business, sells to whoever pays."),
    (r"\bГонт(а|и|і|у|ою)\b", True,
     "Гонта: leader of a group of hunters who came to Затон after a chimera; with his men (Гармата among them) he "
     "tracks big game. His friend Звіробій is on Янів."),
    (r"\bНо(й|я|ю|єм|єві)\b|Ноєв\w*", True,
     "Ной: an old Затон legend: an experienced stalker and completely out of his mind. Lives on an old barge with a "
     "windmill on the roof, which he is turning into an ark to save the stalkers from a coming apocalypse. Has a dog "
     "that even soldiers fear."),
    (r"султан\w*", False,
     "Султан: bandit boss on Затон. His men are tolerated on the «Скадовськ», and he tried to take over Борода's "
     "business; the stalkers put him in his place (or so they tell it)."),
    (r"шульг\w*", False,
     "Підполковник Шульга: commander of «Долг» on Янів station; strict, keeps order."),
    (r"\bлокі\b|\bлоки\b|\bloki\b", False,
     "Локі: head of «Воля» on Янів, in the south wing; an idealist about freedom and the Zone. «Долг» and «Воля» "
     "share Янів only because circumstances forced them."),
    (r"Герман\w*|Германн\w*", True,
     "Професор Герман: head of the scientists' bunker on Юпітер, set up right after Випалювач мізків was switched off; "
     "works with professor Озьорський; pays for measurements and rare finds."),
    (r"озьорськ\w*|озерськ\w*|озерск\w*", False,
     "Професор Озьорський: Герман's colleague in the scientists' bunker on Юпітер."),
    (r"ковальськ\w*|ковальск\w*", False,
     "Полковник Ковальський: commands the army unit stuck in Прип'ять after operation «Фарватер» failed; brought "
     "there by Проводир. Holds his base and waits for evacuation helicopters."),
    (r"Проводир\w*", True,
     "Проводир (the Guide): a legendary stalker who knows every path in the Zone; he led Ковальський's men in."),
    (r"зулус\w*", False,
     "Зулус: a former «Долг» fighter, now on Янів; one of only two people there who can feel an emission coming "
     "(the other is Костоправ, the medic)."),
    (r"костоправ\w*", False,
     "Костоправ: the medic on Янів; he and Зулус can feel an emission coming."),
    (r"соколов\w*", False,
     "Лейтенант Соколов: co-pilot of one of the army helicopters that went down in the Zone; survived."),
    (r"фарватер\w*|\bскат[- ]?\d\b|\bскат(и|ів)\b", False,
     "Operation «Фарватер»: this year the army sent helicopters (callsigns «Скат») to the ЧАЕС; they went down near "
     "Затон and Юпітер, over half the soldiers died. Stalkers loot the wrecks and argue about what brought them down."),
    (r"дегтяр(ьо|е|ё)в\w*", False,
     "Дегтярьов: a stalker who showed up on Затон recently, capable and asking a lot of questions. (Some whisper he "
     "is from the authorities, but nobody knows; don't claim it as fact.) If the player is Дегтярьов, that's him."),
    (r"звіробій\w*", False,
     "Звіробій: a hunter on Янів, Гонта's friend."),
]

COMPILED = [(re.compile(p, 0 if case else re.I), facts) for p, case, facts in LORE]


def lore_for(*texts, limit=3):
    """Facts about the Zone figures named in these texts (at most `limit`), or ""."""
    said = " ".join(t for t in texts if t)
    if not said:
        return ""
    found = []
    for pattern, facts in COMPILED:
        if pattern.search(said) and facts not in found:
            found.append(facts)
        if len(found) >= limit:
            break
    if not found:
        return ""
    return ("Zone lore you know (what a stalker on Затон in 2012 has heard; use it in your own words, as hearsay "
            "where it says rumour, never recite it and add nothing beyond it; if he asks more than this, you don't "
            "know or say it vaguely): " + " ".join(found))
