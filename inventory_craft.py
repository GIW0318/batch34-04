import copy
import math


class InventoryCraft:
    def __init__(self, rows, cols, recipes, stack_limit=20):
        if not self._is_positive_int(rows):
            raise ValueError("rows must be a positive integer")
        if not self._is_positive_int(cols):
            raise ValueError("cols must be a positive integer")
        if not self._is_positive_int(stack_limit):
            raise ValueError("stack_limit must be a positive integer")

        self.rows = rows
        self.cols = cols
        self.stack_limit = stack_limit
        self._cell_count = rows * cols
        self._recipes = copy.deepcopy(recipes or {})
        self._slots = {}
        self._jobs = []
        self._next_job_id = 1

    def add(self, player, item, qty):
        self._validate_name(player, "player")
        self._validate_name(item, "item")
        self._validate_positive_int(qty, "qty")

        grid = self._slots.get(player)
        working = self._copy_grid(grid) if grid is not None else self._empty_grid()
        if not self._can_add(working, item, qty):
            raise ValueError("inventory cannot fit the requested quantity")

        self._add_unchecked(working, item, qty)
        self._slots[player] = working
        return self._count_in_grid(working, item)

    def remove(self, player, item, qty):
        self._validate_name(player, "player")
        self._validate_name(item, "item")
        self._validate_positive_int(qty, "qty")

        grid = self._slots.get(player)
        working = self._copy_grid(grid) if grid is not None else self._empty_grid()
        if self._count_in_grid(working, item) < qty:
            raise ValueError("not enough items to remove")

        self._remove_unchecked(working, item, qty)
        self._slots[player] = working
        return self._count_in_grid(working, item)

    def count(self, player, item):
        self._validate_name(player, "player")
        self._validate_name(item, "item")
        grid = self._slots.get(player)
        if grid is None:
            return 0
        return self._count_in_grid(grid, item)

    def craft(self, player, recipe_id, qty=1, now=0):
        self._validate_name(player, "player")
        self._validate_name(recipe_id, "recipe_id")
        self._validate_number(now, "now")
        self._validate_positive_int(qty, "qty")

        recipe = self._recipes.get(recipe_id)
        if not isinstance(recipe, dict):
            raise ValueError("unknown recipe")

        inputs, output_item, output_per_craft, unit_time = self._parse_recipe(recipe)
        required = [(item, amount * qty) for item, amount in inputs]
        output_qty = output_per_craft * qty
        duration = unit_time * qty

        grid = self._slots.get(player)
        working = self._copy_grid(grid) if grid is not None else self._empty_grid()

        for item, amount in required:
            if self._count_in_grid(working, item) < amount:
                raise ValueError("not enough crafting materials")

        for item, amount in required:
            self._remove_unchecked(working, item, amount)

        if not self._can_add(working, output_item, output_qty):
            raise ValueError("inventory cannot fit the crafting output")

        pending = [job for job in self._jobs if job["status"] == "pending"]
        start = max(now, pending[-1]["end"]) if pending else now
        end = start + duration

        self._slots[player] = working

        job_id = "j{}".format(self._next_job_id)
        self._next_job_id += 1
        self._jobs.append(
            {
                "id": job_id,
                "player": player,
                "recipe_id": recipe_id,
                "recipe": recipe_id,
                "qty": qty,
                "output": output_item,
                "output_item": output_item,
                "output_qty": output_qty,
                "time": duration,
                "start": start,
                "end": end,
                "status": "pending",
            }
        )
        return job_id

    def tick(self, now):
        self._validate_number(now, "now")
        completed = []

        while True:
            job = next(
                (entry for entry in self._jobs if entry["status"] == "pending"),
                None,
            )
            if job is None or now < job["end"]:
                break

            grid = self._slots.get(job["player"])
            working = self._copy_grid(grid) if grid is not None else self._empty_grid()
            if not self._can_add(working, job["output_item"], job["output_qty"]):
                break

            self._add_unchecked(working, job["output_item"], job["output_qty"])
            self._slots[job["player"]] = working
            job["status"] = "completed"
            completed.append(job["id"])

        return completed

    def state(self):
        return {
            "slots": {
                player: self._copy_grid(grid)
                for player, grid in self._slots.items()
            },
            "jobs": copy.deepcopy(self._jobs),
        }

    def _parse_recipe(self, recipe):
        raw_inputs = recipe.get("inputs")
        if not isinstance(raw_inputs, dict):
            raise ValueError("recipe inputs must be a mapping")

        inputs = []
        for item, amount in raw_inputs.items():
            self._validate_name(item, "recipe input")
            self._validate_positive_int(amount, "recipe input quantity")
            inputs.append((item, amount))

        output_item, output_per_craft = self._parse_output(recipe)
        unit_time = recipe.get("time")
        self._validate_number(unit_time, "recipe time")
        if unit_time < 0:
            raise ValueError("recipe time cannot be negative")
        return inputs, output_item, output_per_craft, unit_time

    def _parse_output(self, recipe):
        output = recipe.get("output")
        if isinstance(output, str):
            output_item = output
            output_per_craft = recipe.get(
                "output_qty",
                recipe.get(
                    "output_count",
                    recipe.get("amount", recipe.get("count", 1)),
                ),
            )
        elif isinstance(output, dict):
            if "item" in output or "id" in output:
                output_item = output.get("item", output.get("id"))
                output_per_craft = output.get(
                    "qty", output.get("amount", output.get("count", 1))
                )
            elif len(output) == 1:
                output_item, output_per_craft = next(iter(output.items()))
            else:
                raise ValueError("recipe has an invalid output")
        elif isinstance(output, (list, tuple)) and len(output) == 2:
            output_item, output_per_craft = output
        else:
            raise ValueError("recipe has an invalid output")

        self._validate_name(output_item, "recipe output")
        self._validate_positive_int(output_per_craft, "recipe output quantity")
        return output_item, output_per_craft

    def _empty_grid(self):
        return [None] * self._cell_count

    @staticmethod
    def _copy_grid(grid):
        return [None if slot is None else dict(slot) for slot in grid]

    @staticmethod
    def _count_in_grid(grid, item):
        return sum(
            slot["qty"]
            for slot in grid
            if slot is not None and slot["item"] == item
        )

    def _can_add(self, grid, item, qty):
        capacity = 0
        for slot in grid:
            if slot is None:
                capacity += self.stack_limit
            elif slot["item"] == item:
                capacity += max(0, self.stack_limit - slot["qty"])
        return qty <= capacity

    def _add_unchecked(self, grid, item, qty):
        remaining = qty

        for slot in grid:
            if remaining == 0:
                return
            if slot is None or slot["item"] != item:
                continue
            space = self.stack_limit - slot["qty"]
            if space > 0:
                amount = min(space, remaining)
                slot["qty"] += amount
                remaining -= amount

        for index, slot in enumerate(grid):
            if remaining == 0:
                return
            if slot is not None:
                continue
            amount = min(self.stack_limit, remaining)
            grid[index] = {"item": item, "qty": amount}
            remaining -= amount

        if remaining:
            raise ValueError("inventory cannot fit the requested quantity")

    def _remove_unchecked(self, grid, item, qty):
        remaining = qty
        for index, slot in enumerate(grid):
            if remaining == 0:
                return
            if slot is None or slot["item"] != item:
                continue
            amount = min(slot["qty"], remaining)
            slot["qty"] -= amount
            remaining -= amount
            if slot["qty"] == 0:
                grid[index] = None

        if remaining:
            raise ValueError("not enough items to remove")

    @staticmethod
    def _is_positive_int(value):
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    @classmethod
    def _validate_positive_int(cls, value, name):
        if not cls._is_positive_int(value):
            raise ValueError("{} must be a positive integer".format(name))

    @staticmethod
    def _validate_name(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty string".format(name))

    @staticmethod
    def _validate_number(value, name):
        if isinstance(value, bool):
            raise ValueError("{} must be a finite number".format(name))
        if isinstance(value, int):
            return
        if isinstance(value, float) and math.isfinite(value):
            return
        raise ValueError("{} must be a finite number".format(name))
