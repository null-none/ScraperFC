from tqdm import tqdm
import requests
from bs4 import BeautifulSoup
import pandas as pd
import cloudscraper
from typing import Sequence
import warnings
from .scraperfc_exceptions import InvalidLeagueException, InvalidYearException
from ScraperFC.utils import get_module_comps

TRANSFERMARKT_ROOT = "https://www.transfermarkt.us"

comps = get_module_comps("TRANSFERMARKT")


class Transfermarkt():

    # ==============================================================================================
    def get_valid_seasons(self, league: str) -> dict:
        """ Return valid seasons for the chosen league

        :param str league: .. include:: ./arg_docstrings/league.rst

        :returns: year str is key, ID is value
        :rtype: dict
        """
        if not isinstance(league, str):
            raise TypeError("`league` must be a string.")
        if league not in comps.keys():
            raise InvalidLeagueException(league, "Transfermarkt", list(comps.keys()))

        scraper = cloudscraper.CloudScraper()
        try:
            response = scraper.get(comps[league]["TRANSFERMARKT"])
            soup = BeautifulSoup(response.content, "html.parser")
            season_tags = soup.find("select", {"name": "saison_id"}).find_all("option")  # type: ignore
            valid_seasons = dict([(x.text, x["value"]) for x in season_tags])
            return valid_seasons
        finally:
            scraper.close()

    # ==============================================================================================
    def get_club_links(self, year: str, league: str) -> Sequence[str]:
        """ Gathers all Transfermarkt club URL"s for the chosen league season.

        :param str year: .. include:: ./arg_docstrings/year_transfermarkt.rst
        :param str league: .. include:: ./arg_docstrings/league.rst

        :returns: List of club URLs
        :rtype: List[str]
        """
        if not isinstance(year, str):
            raise TypeError("`year` must be a string.")
        valid_seasons = self.get_valid_seasons(league)
        if year not in valid_seasons.keys():
            raise InvalidYearException(year, league, list(valid_seasons.keys()))

        scraper = cloudscraper.CloudScraper()
        try:
            soup = BeautifulSoup(
                scraper.get(f"{comps[league]['TRANSFERMARKT']}/plus/?saison_id={valid_seasons[year]}").content,
                "html.parser"
            )
            items_table_tag = soup.find("table", {"class": "items"})
            if items_table_tag is None:
                warnings.warn(
                    f"No club links table found for {year} {league}. Returning empty list."
                )
                club_links = list()
            else:
                club_els = items_table_tag.find_all("td", {"class": "hauptlink no-border-links"})  # type: ignore
                club_links = [TRANSFERMARKT_ROOT + x.find("a")["href"] for x in club_els]
            return club_links
        finally:
            scraper.close()

    # ==============================================================================================
    def get_player_links(self, year: str, league: str) -> Sequence[str]:
        """ Gathers all Transfermarkt player URL"s for the chosen league season.

        :param str year: .. include:: ./arg_docstrings/year_transfermarkt.rst
        :param str league: .. include:: ./arg_docstrings/league.rst

        :returns: List of player URLs
        :rtype: List[str]
        """
        player_links = list()
        scraper = cloudscraper.CloudScraper()
        try:
            club_links = self.get_club_links(year, league)
            for club_link in tqdm(club_links, desc=f"{year} {league} player links"):
                soup = BeautifulSoup(scraper.get(club_link).content, "html.parser")
                player_table = soup.find("table", {"class": "items"})
                if player_table is not None:
                    player_els = player_table.find_all("td", {"class": "hauptlink"})  # type: ignore
                    p_links = [
                        TRANSFERMARKT_ROOT + x.find("a")["href"] for x in player_els
                        if x.find("a") is not None
                    ]
                    player_links += p_links
            return list(set(player_links))
        finally:
            scraper.close()

    # ==============================================================================================
    def get_match_links(self, year: str, league: str) -> Sequence[str]:
        """ Returns all match links for a given competition season.

        :param str year: .. include:: ./arg_docstrings/year_transfermarkt.rst
        :param str league: .. include:: ./arg_docstrings/league.rst

        :returns: List of match URLs
        :rtype: List[str]
        """
        valid_seasons = self.get_valid_seasons(league)
        fixtures_url = f"{comps[league]['TRANSFERMARKT'].replace('startseite', 'gesamtspielplan')}/saison_id/{valid_seasons[year]}"
        scraper = cloudscraper.CloudScraper()
        try:
            soup = BeautifulSoup(scraper.get(fixtures_url).content, "html.parser")
            match_tags = soup.find_all("a", {"class": "ergebnis-link"})
            match_links = ["https://www.transfermarkt.us" + x["href"] for x in match_tags]
            return match_links
        finally:
            scraper.close()

    # ==============================================================================================
    def scrape_players(self, year: str, league: str) -> pd.DataFrame:
        """ Gathers all player info for the chosen league season.

        :param str year: .. include:: ./arg_docstrings/year_transfermarkt.rst
        :param str league: .. include:: ./arg_docstrings/league.rst

        :returns: Each row is a player and contains some of the information from their Transfermarkt
        :rtype: pandas.DataFrame
        """
        player_links = self.get_player_links(year, league)
        df = pd.DataFrame()
        for player_link in tqdm(player_links, desc=f"{year} {league} players"):
            player = self.scrape_player(player_link)
            df = pd.concat([df, player], axis=0, ignore_index=True)

        return df

    # ==============================================================================================
    def scrape_player(self, player_link: str) -> pd.DataFrame:
        """ Scrape a single player Transfermarkt link

        :param str player_link: Valid player Transfermarkt URL

        :returns: 1-row dataframe with all of the player details
        :rtype: pandas.DataFrame
        """
        r = requests.get(
            player_link,
            headers={
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +\
                    "(KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"
            }
        )
        soup = BeautifulSoup(r.content, "html.parser")

        # Name
        name_tag = soup.find("h1", {"class": "data-header__headline-wrapper"})
        name = name_tag.text.split("\n")[-1].strip()  # type: ignore

        # Value
        try:
            value_tag = soup.find("a", {"class": "data-header__market-value-wrapper"})
            value = value_tag.text.split(" ")[0]  # type: ignore
            value_last_updated_tag = soup.find("a", {"class": "data-header__market-value-wrapper"})
            value_last_updated = value_last_updated_tag.text.split("Last update: ")[-1]  # type: ignore
        except AttributeError:
            value = None
            value_last_updated = None

        # DOB and age
        dob_el = soup.find("span", {"itemprop": "birthDate"})
        if dob_el is None:
            dob, age = None, None
        else:
            dob = " ".join(dob_el.text.strip().split(" ")[:3])
            age = int(dob_el.text.strip().split(" ")[-1].replace("(", "").replace(")", ""))

        # Height
        height_tag = soup.find("span", {"itemprop": "height"})
        if height_tag is None:
            height = None
        else:
            height_str = height_tag.text.strip()
            if height_str in ["N/A", "- m"]:
                height = None
            else:
                height = float(height_str.replace(" m", "").replace(",", "."))

        # Nationality and citizenships
        nationality_el = soup.find("span", {"itemprop": "nationality"})
        if nationality_el is not None:
            nationality = nationality_el.getText().replace("\n", "").strip()  # type: ignore
        else:
            nationality = None

        citizenship_els = soup.find_all(
            "span", {"class": "info-table__content info-table__content--bold"}
        )
        flag_els = [
            flag_el for el in citizenship_els
            for flag_el in el.find_all("img", {"class": "flaggenrahmen"})
        ]
        citizenship = list(set([el["title"] for el in flag_els]))

        # Position
        position_el = soup.find("dd", {"class": "detail-position__position"})
        if position_el is None:
            position_el = [
                el for el in soup.find_all("li", {"class": "data-header__label"})
                if "position" in el.text.lower()
            ][0].find("span")
        position = position_el.text.strip()
        try:
            other_positions = [
                el.text for el in
                soup.find("div", {"class": "detail-position__position"}).find_all("dd")  # type: ignore
            ]
        except AttributeError:
            other_positions = None
        other_positions = None if other_positions is None else pd.DataFrame(other_positions)  # type: ignore

        # Data header fields
        team = soup.find("span", {"class": "data-header__club"})
        team = None if team is None else team.text.strip()  # type: ignore

        data_headers_labels = soup.find_all("span", {"class": "data-header__label"})
        # Last club
        last_club = [
            x.text.split(":")[-1].strip() for x in data_headers_labels
            if "last club" in x.text.lower()
        ]
        assert len(last_club) < 2
        last_club = None if len(last_club) == 0 else last_club[0]  # type: ignore
        # "Since" date
        since_date = [
            x.text.split(":")[-1].strip() for x in data_headers_labels
            if "since" in x.text.lower()
        ]
        assert len(since_date) < 2
        since_date = None if len(since_date) == 0 else since_date[0]  # type: ignore
        # "Joined" date
        joined_date = [
            x.text.split(":")[-1].strip() for x in data_headers_labels if "joined" in x.text.lower()
        ]
        assert len(joined_date) < 2
        joined_date = None if len(joined_date) == 0 else joined_date[0]  # type: ignore
        # Contract expiration date
        contract_expiration = [
            x.text.split(":")[-1].strip() for x in data_headers_labels
            if "contract expires" in x.text.lower()
        ]
        assert len(contract_expiration) < 2
        contract_expiration = None if len(contract_expiration) == 0 else contract_expiration[0]  # type: ignore

        # Market value history
        try:
            script = [
                s for s in soup.find_all("script", {"type": "text/javascript"})
                if "var chart = new Highcharts.Chart" in str(s)
            ][0]
            values = [int(s.split(",")[0]) for s in str(script).split("y\":")[2:-2]]
            dates = [
                s.split("datum_mw\":")[-1].split(",\"x")[0].replace("\\x20", " ").replace("\"", "")
                for s in str(script).split("y\":")[2:-2]
            ]
            market_value_history = pd.DataFrame({"date": dates, "value": values})
        except IndexError:
            market_value_history = None

        # Transfer History
        rows = soup.find_all("div", {"class": "grid tm-player-transfer-history-grid"})
        transfer_history = pd.DataFrame(
            data=[[s.strip() for s in row.getText().split("\n\n") if s != ""] for row in rows],
            columns=["Season", "Date", "Left", "Joined", "MV", "Fee", ""]
        ).drop(
            columns=[""]
        )

        player = pd.Series(dtype=object)
        player["Name"] = name
        player["ID"] = player_link.split("/")[-1]
        player["Value"] = value
        player["Value last updated"] = value_last_updated
        player["DOB"] = dob
        player["Age"] = age
        player["Height (m)"] = height
        player["Nationality"] = nationality
        player["Citizenship"] = citizenship
        player["Position"] = position
        player["Other positions"] = other_positions
        player["Team"] = team
        player["Last club"] = last_club
        player["Since"] = since_date
        player["Joined"] = joined_date
        player["Contract expiration"] = contract_expiration
        player["Market value history"] = market_value_history
        player["Transfer history"] = transfer_history

        return player.to_frame().T

    # ==============================================================================================
    def scrape_trainer_history(self, trainer_link: str) -> pd.DataFrame:
        """
        Scrape the career history table from a trainer profile.

        Parameters

        trainer_link : str

        Returns

        pandas.DataFrame
        """
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(trainer_link, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        table = soup.find("table", class_="items")
        if table is None:
            return pd.DataFrame()

        # parse header cells
        columns = []
        for th in table.find("thead").find_all("th"):
            # prefer title attr (Matches, PPM), fallback to text
            col = th.get("title") or th.get_text(strip=True)
            columns.append(col)

        # parse body rows
        rows = []
        for tr in table.find("tbody").find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            row = [td.get_text(strip=True) for td in tds]
            # align with header
            if len(row) < len(columns):
                row += [None] * (len(columns) - len(row))
            rows.append(row)

        df = pd.DataFrame(rows, columns=columns)

        # add context
        trainer_name = soup.find("h1").get_text(strip=True) if soup.find("h1") else None
        df.insert(0, "trainer_name", trainer_name)
        df.insert(1, "source_url", trainer_link)

        return df

    # ==============================================================================================
    def scrape_trainer(self, trainer_link: str) -> pd.DataFrame:
        """
        Scrape a trainer profile.

        Parameters

        trainer_link : str
            Transfermarkt trainer profile URL.

        Returns

        pandas.DataFrame
            Single-row dataframe with normalized personal details +
            context columns: ['trainer_name', 'source_url', ...].
        """
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        r = requests.get(trainer_link, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # helpers
        def squash(s: str) -> str:
            return " ".join((s or "").split())

        def norm_key(raw: str) -> str:
            """
            Normalize visible header labels to stable snake_case,
            then apply a small mapping to unify common variants.
            """
            k = (raw or "").lower().strip()
            k = k.replace(":", "").replace("/", " ")
            k = " ".join(k.split())
            k = k.replace(" ", "_")
            mapping = {
                "name_in_home_country": "full_name_native",
                "full_name": "full_name_native",
                "date_of_birth_age": "date_of_birth_age",
                "date_of_birth": "date_of_birth_age",
                "place_of_birth": "place_of_birth",
                "citizenship": "citizenship",
                "avg._term_as_trainer": "avg_term_as_trainer",
                "avg_term_as_trainer": "avg_term_as_trainer",
                "trainering_licence": "trainering_licence",
                "preferred_formation": "preferred_formation",
            }
            return mapping.get(k, k)

        # context: trainer name from <h1>
        trainer_name = None
        h1 = soup.find("h1")
        if h1:
            trainer_name = squash(h1.get_text())

        # collect from all .data-header__details blocks (desktop/mobile variants)
        data = {}
        for details in soup.select(".data-header__details"):
            # inside, each row is typically a <li> where:
            #   - direct text node (before <span>) is the key label
            #   - <span class="data-header__content"> contains the value
            for li in details.find_all("li", class_="data-header__label"):
                # direct text of <li> (not including nested <span>)
                key_text = li.find(text=True, recursive=False)
                if not key_text:
                    # fallback: use first stripped string up to colon
                    key_text = li.get_text(separator=" ", strip=True).split(":")[0]
                key = norm_key(squash(key_text))

                span = li.find("span", class_="data-header__content")
                val = squash(span.get_text()) if span else None

                # store last non-empty value wins
                if val:
                    data[key] = val

        # build final row (keep values as-is, no extra parsing)
        row = {
            "trainer_name": trainer_name,
            "source_url": trainer_link,
            # commonly present fields; safe .get() if some keys absent
            "full_name_native": data.get("full_name_native"),
            "date_of_birth_age": data.get("date_of_birth_age"),
            "place_of_birth": data.get("place_of_birth"),
            "citizenship": data.get("citizenship"),
            "avg_term_as_trainer": data.get("avg_term_as_trainer"),
            "trainering_licence": data.get("trainering_licence"),
            "preferred_formation": data.get("preferred_formation"),
        }

        # also include any additional normalized keys that appeared in the header
        # but weren't in the predefined list
        for k, v in data.items():
            if k not in row:
                row[k] = v

        return pd.DataFrame([row])
