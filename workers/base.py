class BaseWorker:
    def __init__(self, command_timeout, global_topic_prefix, **kwargs):
        self.command_timeout = command_timeout
        self.global_topic_prefix = global_topic_prefix
        self.fail_count = 0
        self.max_fail_count = 5
        self.last_updated = None

        for arg, value in kwargs.items():
            setattr(self, arg, value)
        self._setup()

    def _setup(self):
        return

    def format_discovery_topic(self, mac, *sensor_args):
        node_id = mac.replace(":", "").lower()
        object_id = "_".join([repr(self), *sensor_args])
        return "{}/{}".format(node_id, object_id)

    def format_discovery_id(self, mac, *sensor_args):
        return "{}".format(self.format_discovery_topic(mac, *sensor_args))

    def format_discovery_name(self, mac, *sensor_args):
        node_id = mac.replace(":", "").lower()
        if len(sensor_args) != 0:
            return "_".join([*sensor_args, node_id])
        return node_id

    def format_topic(self, *topic_args):
        return "/".join([self.topic_prefix, *topic_args])

    def format_prefixed_topic(self, *topic_args):
        topic = self.format_topic(*topic_args)
        if self.global_topic_prefix:
            return "{}/{}".format(self.global_topic_prefix, topic)
        return topic

    def __repr__(self):
        return self.__module__.split(".")[-1]

    @staticmethod
    def true_false_to_ha_on_off(true_false):
        if true_false:
            return 'ON'

        return 'OFF'


