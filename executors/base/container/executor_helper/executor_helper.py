import json
import sys


class ExecutorHelper:
    def __init__(self):
        self._errors = []
        self._warnings = []
        self._infos = []

        self._input_entities = {}
        self._output_entities = {}

        self._configuration = {}

        self._used_input_entitytypes = set()

    def read_input(self):
        with open("/data/input/data.json", "r") as f:
            data = json.load(f)
            self._input_entities = data.get("data", {})
            self._configuration = data.get("configuration", {})

    def write_output(self):
        # check if all provided entitytypes were used, otherwise add warning
        provided_types = set(self._input_entities.keys())
        used_types = set(self._used_input_entitytypes)
        unused_types = provided_types - used_types
        if unused_types:
            self.add_warning("provided entitytypes were not used: {}".format(", ".join(unused_types)))

        # and then write output
        data = {
            "errors": self._errors,
            "warnings": self._warnings,
            "infos": self._infos,
            "data": self._output_entities,
        }

        with open("/data/output/data.json", "w") as f:
            json.dump(data, f)

    def get_config(self, name, default=None, required=False):
        value = self._configuration.get(name, default)
        # if no value is set in the app, "null" is set in the config -> we want to use the default
        if value is None:
            value = default

        if required and value is None:
            self.add_error(f'required configuration option "{name}" not set')
        return value

    def get_config_bool(self, name, default=None, required=False):
        """
        Returns config as boolean.
        The strings "0"/"1", "true"/"false" and "yes"/"no" are mapped to boolean values (case-insensitive).
        Other values are rejected.
        """
        value = self.get_config(name, default, required)
        if value is None:
            return

        # if the default value is used, it might be a boolean already
        if type(value) == bool:
            return value

        # map some values to True or False
        if value.lower() in ["0", "false", "no"]:
            return False
        elif value.lower() in ["1", "true", "yes"]:
            return True
        else:
            self.add_error(
                f'configuration option "{name}" has invalid type - expected boolean (0/1, true/false, yes/no)'
            )

    def get_config_choices(self, name, default=None, required=False, choices=[]):
        """
        Returns config and validates that it is a valid choice.
        The comparison is case-insensitive and a lower case string is returned.
        """
        value = self.get_config(name, default, required)
        if value is None:
            return

        # check if value is in choices
        choices_lower = [x.lower() for x in choices]
        value_lower = value.lower()
        if value_lower not in choices_lower:
            self.add_error(f'configuration option "{name}" has invalid value - allowed: {", ".join(choices_lower)}')
        else:
            return value_lower

    def get_input_entities(self, entitytype):
        try:
            data = self._input_entities[entitytype]
            self._used_input_entitytypes.add(entitytype)
            return data
        except KeyError:
            return []

    def add_output_entity(self, entitytype, data):
        # if this is the first entity of this type, create the list
        if entitytype not in self._output_entities:
            self._output_entities[entitytype] = []

        # add it
        self._output_entities[entitytype].append(data)

    def add_error(self, message):
        self._errors.append(message)

    def add_warning(self, message):
        self._warnings.append(message)

    def add_info(self, message):
        self._infos.append(message)

    def exit_on_error(self):
        if len(self._errors) > 0:
            self.write_output()

            # return code 0 is fine here as the logged error(s) will lead to a fail
            sys.exit(0)
