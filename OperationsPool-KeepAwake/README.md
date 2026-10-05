# Operations Pool keep-awake

Double-click `Start-OperationsPool-KeepAwake.cmd` while the Omnissa Horizon window
whose title is **Operations Pool** is open.

A small local status window shows the time remaining:

- Green means the eight-hour keep-awake period is running normally.
- Yellow means 30 minutes or less remain.
- At zero, automatic pulses stop and the window tells you to close it and run the
  launcher again.

The utility schedules the normally unused F15 key every two minutes. If you are
actively working inside Horizon, your real input already keeps the VDI awake and
the automatic pulse waits until you pause. When another local application is in
front, the utility posts directly to Horizon's remembered input control. It does
not take focus, block clicks, or wait for activity in unrelated applications.

While Windows is locked with **Win+L**, the utility prevents automatic system
sleep and queues F15 directly to Horizon's UI thread without unlocking Windows or
changing the secure desktop. The log identifies these as `locked/background`
pulses. Windows deliberately blocks normal foreground input on the lock screen,
so only a helper running inside the VDI or an administrator-managed Horizon idle
policy can guarantee that a locked-state message is accepted by the remote side.
Manually putting the computer to sleep suspends all local programs, including this
one; locking and sleeping are different operations.

Close the status window or select **Stop and close** to stop early.

Use this only where keeping the VDI session active is permitted by your
organisation's security policy.
