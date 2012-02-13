import numpy as np
from spharm import Spharmt, getspecindx
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap, addcyclic
import time

# non-linear barotropically unstable shallow water test case
# of Galewsky et al (2004, Tellus, 56A, 429-440).
# "An initial-value problem for testing numerical models of the global
# shallow-water equations"
# http://www-vortex.mcs.st-and.ac.uk/~rks/reprints/galewsky_etal_tellus_2004.pdf

# grid, time step info
nlons = 256  # number of longitudes
ntrunc = nlons/3 # spectral truncation (for alias-free computations)
nlats = (nlons/2)+1 # for regular grid.
gridtype = 'regular'
dt = 150 # time step in seconds
itmax = 6*(86400/dt) # integration length in days

pi = np.pi; d2r = pi/180.
# parameters for test
rsphere = 6.37122e6 # earth radius
omega = 7.292e-5 # rotation rate
grav = 9.80616 # gravity
hbar = 10.e3 # resting depth
umax = 80. # jet speed
phi0 = pi/7.; phi1 = 0.5*pi - phi0; phi2 = 0.25*pi
en = np.exp(-4.0/(phi1-phi0)**2)
alpha = 1./3.; beta = 1./15.
hamp = 120. # amplitude of height perturbation to zonal jet
efold = 3.*3600. # efolding timescale at ntrunc for hyperdiffusion
ndiss = 8 # order for hyperdiffusion

# setup up spherical harmonic instance, set lats/lons of grid

x = Spharmt(nlons,nlats,rsphere,gridtype=gridtype)
delta = 2.*pi/nlons
lats1d = 0.5*pi-delta*np.arange(nlats)
lons1d = np.arange(-pi,pi,delta)
lons,lats = np.meshgrid(lons1d,lats1d)
f = 2.*omega*np.sin(lats) # coriolis

# zonal jet.
vg = np.zeros((nlats,nlons),np.float32)
u1 = (umax/en)*np.exp(1./((lats1d-phi0)*(lats1d-phi1)))
ug = np.zeros((nlats),np.float32)
ug = np.where(np.logical_and(lats1d < phi1, lats1d > phi0), u1, ug)
ug.shape = (nlats,1)
ug = ug*np.ones((nlats,nlons),dtype=np.float32) # broadcast to shape (nlats,nlonss)
# height perturbation.
hbump = hamp*np.cos(lats)*np.exp(-(lons/alpha)**2)*np.exp(-(phi2-lats)**2/beta)

# initial vorticity, divergence in spectral space
vrtspec, divspec =  x.getvrtdivspec(ug,vg,ntrunc)

# create spectral indexing arrays, laplacian operator and its inverse.
indxm, indxn = getspecindx(ntrunc)
lap = -(indxn*(indxn+1.0)/rsphere**2).astype(np.float32)
ilap = np.zeros(lap.shape, np.float32)
ilap[1:] = 1./lap[1:]
hyperdiff_fact = np.exp((-dt/efold)*(lap/lap[-1])**(ndiss/2))

# solve nonlinear balance eqn to get initial zonal geopotential,
# add localized bump (not balanced).
vrtg = x.spectogrd(vrtspec)
scrg1 = ug*(vrtg+f); scrg2 = vg*(vrtg+f)
tmpspec1,tmpspec2 = x.getvrtdivspec(scrg1,scrg2,ntrunc)
tmpspec2 = x.grdtospec(0.5*(ug**2+vg**2),ntrunc)
phispec = ilap*tmpspec1 - tmpspec2
phig = grav*(hbar + hbump) + x.spectogrd(phispec)
phispec = x.grdtospec(phig,ntrunc)

# initialize spectral tendency arrays
ddivdtspec = np.zeros(vrtspec.shape+(3,), np.complex64)
dvrtdtspec = np.zeros(vrtspec.shape+(3,), np.complex64)
dphidtspec = np.zeros(vrtspec.shape+(3,), np.complex64)
nnew = 0; nnow = 1; nold = 2

# time step loop.

time1 = time.clock()
for ncycle in range(itmax+1):
    t = ncycle*dt
# get vort,u,v,phi on grid
    vrtg = x.spectogrd(vrtspec)
    ug,vg = x.getuv(vrtspec,divspec)
    phig = x.spectogrd(phispec)
    print 't=%6.2f hours: min/max %6.2f, %6.2f' % (t/3600.,vg.min(), vg.max())
# compute tendencies.
    scrg1 = ug*(vrtg+f); scrg2 = vg*(vrtg+f)
    ddivdtspec[:,nnew],dvrtdtspec[:,nnew] = x.getvrtdivspec(scrg1,scrg2,ntrunc)
    dvrtdtspec[:,nnew] *= -1
    scrg1 = ug*phig; scrg2 = vg*phig
    tmpspec, dphidtspec[:,nnew] = x.getvrtdivspec(scrg1,scrg2,ntrunc)
    dphidtspec[:,nnew] *= -1
    tmpspec = x.grdtospec(phig+0.5*(ug**2+vg**2),ntrunc)
    ddivdtspec[:,nnew] += -lap*tmpspec
# update vort,div,phiv with third-order adams-bashforth.
# forward euler, then 2nd-order adams-bashforth time steps to start.
    if ncycle == 0:
        dvrtdtspec[:,nnow] = dvrtdtspec[:,nnew]
        dvrtdtspec[:,nold] = dvrtdtspec[:,nnew]
        ddivdtspec[:,nnow] = ddivdtspec[:,nnew]
        ddivdtspec[:,nold] = ddivdtspec[:,nnew]
        dphidtspec[:,nnow] = dphidtspec[:,nnew]
        dphidtspec[:,nold] = dphidtspec[:,nnew]
    elif ncycle == 1:
        dvrtdtspec[:,nold] = dvrtdtspec[:,nnew]
        ddivdtspec[:,nold] = ddivdtspec[:,nnew]
        dphidtspec[:,nold] = dphidtspec[:,nnew]
    vrtspec += dt*( \
    (23./12.)*dvrtdtspec[:,nnew] - (16./12.)*dvrtdtspec[:,nnow]+ \
    (5./12.)*dvrtdtspec[:,nold] )
    divspec += dt*( \
    (23./12.)*ddivdtspec[:,nnew] - (16./12.)*ddivdtspec[:,nnow]+ \
    (5./12.)*ddivdtspec[:,nold] )
    phispec += dt*( \
    (23./12.)*dphidtspec[:,nnew] - (16./12.)*dphidtspec[:,nnow]+ \
    (5./12.)*dphidtspec[:,nold] )
    # implicit hyperdiffusion for vort and div.
    vrtspec *= hyperdiff_fact
    divspec *= hyperdiff_fact
# switch indices, do next time step.
    nsav1 = nnew
    nsav2 = nnow
    nnew = nold
    nnow = nsav1
    nold = nsav2

time2 = time.clock()
print 'CPU time = ',time2-time1

# make a NH Lambert aziumthal plot.
m = Basemap(projection='nplaea',boundinglat=1,lon_0=270,round=True)
vrtg,lons1d = addcyclic(vrtg,lons1d/d2r)
lons, lats = np.meshgrid(lons1d,lats1d/d2r)
x,y = m(lons,lats)
levs = np.arange(-1.5e-4,1.501e-4,1.5e-5)
m.drawmeridians(np.arange(-180,181,60))
m.drawparallels(np.arange(20,81,20))
CS=m.contourf(x,y,vrtg,levs,cmap=plt.cm.spectral,extend='both')
m.colorbar()
plt.title('vorticity (T%s with hyperdiffusion, hour %6.2f)' % (ntrunc,t/3600.))
plt.show()
