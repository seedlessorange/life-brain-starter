-- Brain Server.app: keeps the brain's server running while it is open.
-- Built by brain/tools/make_brain_app.sh. Everything it does is in
-- brain/tools/brain_app.sh; this file stays fixed, because macOS ties Full
-- Disk Access to the app's exact build. No properties or globals on purpose:
-- an applet writes those back into itself on quit, which would change the
-- build and silently cost it the permission.

on brain(what)
	set root to do shell script "dirname " & quoted form of (POSIX path of (path to me))
	return do shell script "/bin/zsh -lc " & quoted form of (quoted form of (root & "/brain/tools/brain_app.sh") & " " & what)
end brain

on run
	brain("start")
end run

-- Clicking the Dock icon opens the page.
on reopen
	brain("open")
end reopen

-- A heartbeat: if the server died, it comes back.
on idle
	try
		brain("ensure")
	end try
	return 60
end idle

on quit
	set busy to "no"
	try
		set busy to brain("busy")
	end try
	if busy is "yes" then
		try
			set r to display dialog "Claude is still working on something for you. Stop the brain anyway?" buttons {"Keep it running", "Stop"} default button "Keep it running" with title "Brain"
			if button returned of r is "Keep it running" then return
		on error
			return
		end try
	end if
	try
		brain("stop")
	end try
	continue quit
end quit
