package mountsvc

import (
	"time"

	"golang.org/x/net/webdav"
)

// cappedMemLS wraps webdav.NewMemLS() and caps lock duration so that locks
// acquired before a failed upload don't linger for Windows' default 1-hour
// timeout. After a failed PUT, the lock expires within maxLock seconds and
// Windows can retry with a fresh LOCK → PUT sequence.
type cappedMemLS struct {
	inner   webdav.LockSystem
	maxLock time.Duration
}

func newCappedMemLS(max time.Duration) webdav.LockSystem {
	return &cappedMemLS{inner: webdav.NewMemLS(), maxLock: max}
}

func (ls *cappedMemLS) Confirm(now time.Time, name0, name1 string, conditions ...webdav.Condition) (func(), error) {
	return ls.inner.Confirm(now, name0, name1, conditions...)
}

func (ls *cappedMemLS) Create(now time.Time, details webdav.LockDetails) (string, error) {
	if details.Duration < 0 || details.Duration > ls.maxLock {
		details.Duration = ls.maxLock
	}
	return ls.inner.Create(now, details)
}

func (ls *cappedMemLS) Refresh(now time.Time, token string, duration time.Duration) (webdav.LockDetails, error) {
	if duration < 0 || duration > ls.maxLock {
		duration = ls.maxLock
	}
	return ls.inner.Refresh(now, token, duration)
}

func (ls *cappedMemLS) Unlock(now time.Time, token string) error {
	return ls.inner.Unlock(now, token)
}
