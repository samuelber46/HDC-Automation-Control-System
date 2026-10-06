# opc/client.py

import time

import win32com.client
import pythoncom


class OPCConnectionError(RuntimeError):
    """Raised when the OPC connection is no longer usable."""


class OPCClient:

    def __init__(
        self,
        server_name,
        group_name="PythonGroup",
        update_rate=1000,
        reconnect_delay=2.0,
    ):

        self.server_name = server_name
        self.group_name = group_name
        self.update_rate = update_rate
        self.reconnect_delay = reconnect_delay

        self.opc = None
        self.groups = None
        self.group = None

        # Alias -> OPC Item
        self.items = {}

        # Alias -> Full OPC Tag
        self.tag_names = {}

        self._com_initialized = False
        self.connected = False
        self.last_read_success = False
        self.consecutive_read_failures = 0

        # OPC diagnostics: alias -> Quality / Timestamp
        self.last_quality = {}
        self.last_timestamp = {}

    # ==================================================
    # COM INITIALIZATION
    # ==================================================

    def _ensure_com_initialized(self):
        if not self._com_initialized:
            pythoncom.CoInitialize()
            self._com_initialized = True

    # ==================================================
    # CONNECT
    # ==================================================

    def connect(self):
        """Create a fresh OPC Automation connection and group."""

        self._ensure_com_initialized()

        # Always start from a clean COM state.
        self._release_com_objects(uninitialize=False)

        print(
            f"[OPC] Connecting to {self.server_name}"
        )

        try:
            self.opc = win32com.client.Dispatch(
                "OPC.Automation.1"
            )

            self.opc.Connect(
                self.server_name
            )

            self.groups = self.opc.OPCGroups

            self.group = self.groups.Add(
                self.group_name
            )

            self.group.IsActive = True
            self.group.IsSubscribed = False
            self.group.UpdateRate = self.update_rate

            self.connected = True
            self.last_read_success = False
            self.consecutive_read_failures = 0

            print("[OPC] Connected")

        except Exception:
            self.connected = False
            self._release_com_objects(uninitialize=False)
            raise

    # ==================================================
    # ADD ITEM
    # ==================================================

    def add_item(self, name, tag):

        if self.group is None:
            raise OPCConnectionError(
                "OPC group is not connected"
            )

        try:
            item = self.group.OPCItems.AddItem(
                tag,
                len(self.items) + 1
            )

            self.items[name] = item
            self.tag_names[name] = tag

            print(
                f"[OPC] Added: {name} -> {tag}"
            )

            return item

        except Exception as e:
            self.connected = False
            print(
                f"[OPC ADD ERROR] {name} -> {tag}: {repr(e)}"
            )
            raise

    # ==================================================
    # ADD MULTIPLE ITEMS
    # ==================================================

    def add_items(self, tags):

        # Item aliases are rebuilt after every reconnect.
        self.items.clear()
        self.tag_names.clear()
        self.last_quality.clear()
        self.last_timestamp.clear()

        for name, tag in tags.items():
            self.add_item(name, tag)

    # ==================================================
    # RECONNECT
    # ==================================================

    def reconnect(self, tags=None):
        """Cleanly rebuild the OPC COM connection and all OPC items."""

        print(
            f"[OPC] Reconnecting in {self.reconnect_delay:.1f}s..."
        )

        time.sleep(self.reconnect_delay)

        self.close()
        self.connect()

        if tags is not None:
            self.add_items(tags)

        print("[OPC] Reconnected successfully")

    # ==================================================
    # READ
    # ==================================================

    def read(self, name):

        if not self.connected or name not in self.items:
            raise OPCConnectionError(
                f"OPC item not available: {name}"
            )

        item = self.items[name]

        try:
            result = item.Read(1)
            value = self.extract_value(result)
            self.last_read_success = True
            self.consecutive_read_failures = 0
            return value

        except Exception as e:
            self.connected = False
            raise OPCConnectionError(
                f"OPC read failed for {name}: {repr(e)}"
            ) from e

    # ==================================================
    # READ ALL
    # ==================================================

    def read_all(self):

        if not self.connected or not self.items:
            raise OPCConnectionError(
                "OPC connection/items are not available"
            )

        data = {}
        successful_reads = 0

        for name, item in self.items.items():

            try:
                result = item.Read(1)
                value, quality, timestamp = self.extract_state(result)
                data[name] = value
                self.last_quality[name] = quality
                self.last_timestamp[name] = timestamp
                successful_reads += 1

            except Exception as e:
                data[name] = None
                print(
                    f"[OPC READ ERROR] {name}: {repr(e)}"
                )

        # If every item failed in one cycle, the OPC connection is
        # considered unusable and the main loop will reconnect it.
        if successful_reads == 0:
            self.connected = False
            self.last_read_success = False
            self.consecutive_read_failures += 1
            raise OPCConnectionError(
                "All OPC item reads failed"
            )

        self.connected = True
        self.last_read_success = True
        self.consecutive_read_failures = 0

        return data

    # ==================================================
    # WRITE
    # ==================================================

    def write(self, name, value):

        if not self.connected or name not in self.items:
            raise OPCConnectionError(
                f"OPC item not available: {name}"
            )

        item = self.items[name]

        try:
            item.Write(value)

        except Exception as e:
            self.connected = False
            raise OPCConnectionError(
                f"OPC write failed for {name}: {repr(e)}"
            ) from e

    # ==================================================
    # GET ITEM
    # ==================================================

    def get_item(self, name):

        if name not in self.items:
            raise KeyError(
                f"OPC item not found: {name}"
            )

        return self.items[name]

    # ==================================================
    # GET TAG NAME
    # ==================================================

    def get_tag_name(self, name):

        if name not in self.tag_names:
            raise KeyError(
                f"OPC item not found: {name}"
            )

        return self.tag_names[name]

    # ==================================================
    # COM CLEANUP
    # ==================================================

    def _release_com_objects(self, uninitialize=False):
        """Release COM references in dependency order."""

        self.connected = False
        self.last_read_success = False

        # Release item wrappers first.
        self.items.clear()
        self.tag_names.clear()

        # Drop group and OPCGroups references before the server object.
        self.group = None
        self.groups = None

        try:
            if self.opc is not None:
                try:
                    self.opc.Disconnect()
                except Exception:
                    pass
        finally:
            self.opc = None

        if uninitialize and self._com_initialized:
            try:
                pythoncom.CoUninitialize()
            finally:
                self._com_initialized = False

    # ==================================================
    # CLOSE
    # ==================================================

    def close(self):
        """Disconnect and fully release OPC/COM resources."""

        try:
            self._release_com_objects(uninitialize=True)
            print("[OPC] COM resources released")

        except Exception as e:
            print(
                f"[OPC] Cleanup error: {repr(e)}"
            )

    # ==================================================
    # VALUE EXTRACTION
    # ==================================================

    @staticmethod
    def extract_state(result):
        """Extract Value, Quality and Timestamp from OPC Automation Read().

        Important: for tuple/list results the first element is Value.
        The second element is Quality (often 192 / 0xC0 for OPC_QUALITY_GOOD),
        NOT the process value.
        """

        if hasattr(result, "Value"):
            value = result.Value
            quality = getattr(result, "Quality", None)
            timestamp = getattr(result, "Timestamp", None)
            return value, quality, timestamp

        if isinstance(result, (tuple, list)):
            if len(result) >= 3:
                return result[0], result[1], result[2]
            if len(result) == 2:
                return result[0], result[1], None
            if len(result) == 1:
                return result[0], None, None

        return result, None, None

    @staticmethod
    def extract_value(result):
        """Backward-compatible helper returning only the OPC Value."""
        value, _, _ = OPCClient.extract_state(result)
        return value

    def get_quality(self, name):
        return self.last_quality.get(name)

    def get_timestamp(self, name):
        return self.last_timestamp.get(name)
