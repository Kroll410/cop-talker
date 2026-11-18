"""Copy the two original game scripts into the mod and add one-line hooks.

Usage: python patch_hooks.py <original_scripts_dir> <mod_scripts_dir>
Works on raw bytes so the cp1251 comments in the originals stay intact.
"""
import os
import sys

# A hunting squad's target may be one the simulation hides (in a safe base): look it up directly then.
HUNT_FALLBACK = (b"\tif squad_target == nil and talker_bridge.is_hunting and talker_bridge.is_hunting(squad) then "
                 b"squad_target = alife():object(squad.assigned_target_id) end\r\n")

HOOKS = {
    "bind_stalker.script": [
        (b"function actor_binder:update(delta)\r\n\tobject_binder.update(self, delta)\r\n",
         b"\ttalker_bridge.safe(talker_bridge.update, delta)\r\n"),
        (b"function actor_binder:on_item_take (obj)\r\n",
         b"\ttalker_bridge.safe(talker_bridge.on_item_take, obj)\r\n"),
    ],
    "xr_motivator.script": [
        (b"function motivator_binder:hit_callback(obj, amount, local_direction, who, bone_index)\r\n",
         b"\ttalker_bridge.safe(talker_bridge.on_npc_hit, obj, amount, who)\r\n"),
        (b"function motivator_binder:death_callback(victim, who)\r\n",
         b"\ttalker_bridge.safe(talker_bridge.on_npc_death, victim, who)\r\n"),
        (b"function motivator_binder:use_callback(obj, who)\r\n",
         b"\ttalker_bridge.safe(talker_bridge.on_npc_use, obj, who)\r\n"),
    ],
    # Bases (Skadovsk, Yanov...) forbid NPC fights; a paid hit agreed in conversation is let through.
    "xr_combat_ignore.script": [
        (b"function is_enemy(obj, enemy, st, not_check_sim)\r\n\tif not obj:alive() then\r\n\t\treturn false\r\n\tend\r\n",
         b"\tif talker_bridge.is_contract and talker_bridge.is_contract(obj, enemy) then\r\n\t\treturn true\r\n\tend\r\n"),
    ],
    # A paid hit on a man far away: the killer's squad hunts the target's squad with the game's own "attack a
    # squad" move, even where the simulation wouldn't send it (safe bases, faction rules). "*" = every match.
    "sim_squad_scripted.script": [
        (b"function sim_squad_scripted:assigned_target_avaliable()\r\n",
         b"\tif talker_bridge.is_hunting and talker_bridge.is_hunting(self) then\r\n"
         b"\t\treturn alife():object(self.assigned_target_id) ~= nil\r\n\tend\r\n"),
    ],
    "sim_squad_actions.script": [
        (b"*\tlocal squad_target = simulation_objects.get_sim_obj_registry().objects[squad.assigned_target_id]\r\n",
         HUNT_FALLBACK),
    ],
    "xr_reach_task.script": [
        (b"*\tlocal squad_target = simulation_objects.get_sim_obj_registry().objects[squad.assigned_target_id]\r\n",
         HUNT_FALLBACK),
    ],
}


def main():
    src_dir, dst_dir = sys.argv[1:]
    os.makedirs(dst_dir, exist_ok=True)
    for name, hooks in HOOKS.items():
        data = open(os.path.join(src_dir, name), "rb").read()
        for anchor, line in hooks:
            every = anchor.startswith(b"*")
            anchor = anchor[1:] if every else anchor
            if data.count(anchor) < 1 or (not every and data.count(anchor) != 1):
                raise SystemExit(f"{name}: anchor not found{'' if every else ' exactly once'}: {anchor!r}")
            data = data.replace(anchor, anchor + line)
        with open(os.path.join(dst_dir, name), "wb") as fh:
            fh.write(data)
        print(f"patched {name} ({len(hooks)} hooks)")


if __name__ == "__main__":
    main()
