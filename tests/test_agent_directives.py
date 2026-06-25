"""agent-directives — structural verification of the shared-spine composition.

Behavior is unchanged (the LLM mocks ignore ``system=``); these assert the prose
contract: every agent's system prompt carries the four SPINE rules, the six
public-facing agents carry VOICE, the three analysis agents do not, and the three
builder agents still interpolate the brand voice fields.
"""

import unittest

from orion_os_cmo.llm.principles import SPINE, VOICE, compose

# Static-_SYSTEM agents expose `_SYSTEM`.
from orion_os_cmo.agent_seo import agent as seo_agent
from orion_os_cmo.agent_geo import agent as geo_agent
from orion_os_cmo.agent_coding import agent as coding_agent
from orion_os_cmo.agent_reddit import agent as reddit_agent
from orion_os_cmo.agent_influencer import agent as influencer_agent
from orion_os_cmo.agent_ugc import agent as ugc_agent
# Builder agents expose a prompt-building function.
from orion_os_cmo.agent_writer.agent import _system as writer_system
from orion_os_cmo.agent_x import build_x_prompt
from orion_os_cmo.agent_linkedin import build_linkedin_prompt

# Markers — a stable sentence fragment from each SPINE rule + the VOICE addendum.
SPINE_MARKERS = [
    "Draft for review, never for the world",   # rule 1
    "Ground every fact",                        # rule 2
    "Work inside the brand's strategy",         # rule 3
    "Depth over volume",                        # rule 4
]
VOICE_MARKER = "Write in the brand voice exactly as given"

STRATEGY = {"sections": {"brand_voice": {
    "tone": "TONE-MARKER", "register": "REG-MARKER",
    "do": ["be concrete"], "dont": ["hype"], "sample_phrases": ["ship it"]}}}

NO_VOICE = {"seo": seo_agent._SYSTEM, "geo": geo_agent._SYSTEM, "coding": coding_agent._SYSTEM}
VOICE_STATIC = {"reddit": reddit_agent._SYSTEM, "influencer": influencer_agent._SYSTEM,
                "ugc": ugc_agent._SYSTEM}


class Directives(unittest.TestCase):
    def test_all_nine_carry_the_spine(self):
        builders = {
            "writer": writer_system(STRATEGY),
            "x": build_x_prompt(STRATEGY["sections"])[0],
            "linkedin": build_linkedin_prompt(STRATEGY["sections"])[0],
        }
        for name, system in {**NO_VOICE, **VOICE_STATIC, **builders}.items():
            for marker in SPINE_MARKERS:
                self.assertIn(marker, system, f"{name} missing SPINE rule: {marker}")

    def test_voice_assignment(self):
        # The three analysis agents must NOT carry VOICE.
        for name, system in NO_VOICE.items():
            self.assertNotIn(VOICE_MARKER, system, f"{name} should not carry VOICE")
        # The six public-facing agents MUST carry VOICE.
        voice_systems = {**VOICE_STATIC,
                         "writer": writer_system(STRATEGY),
                         "x": build_x_prompt(STRATEGY["sections"])[0],
                         "linkedin": build_linkedin_prompt(STRATEGY["sections"])[0]}
        for name, system in voice_systems.items():
            self.assertIn(VOICE_MARKER, system, f"{name} should carry VOICE")

    def test_builders_still_interpolate_brand_voice(self):
        for name, system in {
            "writer": writer_system(STRATEGY),
            "x": build_x_prompt(STRATEGY["sections"])[0],
            "linkedin": build_linkedin_prompt(STRATEGY["sections"])[0],
        }.items():
            self.assertIn("TONE-MARKER", system, f"{name} dropped tone interpolation")
            self.assertIn("REG-MARKER", system, f"{name} dropped register interpolation")

    def test_ugc_now_has_anti_fabrication(self):
        # The previously-ungrounded agent now carries the grounding rule (via SPINE)
        # plus an explicit on-screen honesty directive in its role block.
        self.assertIn("Ground every fact", ugc_agent._SYSTEM)
        self.assertIn("substantiate", ugc_agent._SYSTEM)

    def test_compose_shape(self):
        self.assertTrue(compose("ROLE").startswith(SPINE))
        self.assertNotIn(VOICE, compose("ROLE"))
        self.assertIn(VOICE, compose("ROLE", voice=True))
        self.assertTrue(compose("ROLE", voice=True).endswith("ROLE"))


if __name__ == "__main__":
    unittest.main()
