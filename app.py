#!/usr/bin/env python3
"""MQTTPlot entrypoint (compatibility wrapper).

As of v0.6.2, the application code lives in the mqttplot/ package.
This file remains for backward compatibility with existing service files.
"""

from mqttplot.app import main

if __name__ == "__main__":
    main()
