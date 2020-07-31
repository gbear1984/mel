import os

numPlanes = 25

# Get the path to the current working directory.
# For example, "/stuhome/vsfx319/cutter"
cwd = os.getcwd()

# Get the path to the parent directory
# and the name of the cwd
parent,name = os.path.split(cwd)

# Make a path to the archives directory
archives = os.path.join(parent, "archives")

# Finally, the path to the rib archive this
# script will generate
ribpath = os.path.join(archives, "planes.rib")
#print ribpath

# Open the output rib file
fileid = open(ribpath, 'w')

zIncr = 1.0/numPlanes

zTranslate = '\t\tTranslate 0 0 %1.3f\n' % zIncr
# Because all the polygons are the same we can
# define the RIB statement once and once only
shape = '\t\tPolygon "P" [-0.5 0.5 0   -0.5 -0.5 0   0.5 -0.5 0   0.5 0.5 0]\n'
shape += '\t\t	   "st" [0 0  0 1  1 1  1 0]\n'

# It is assumed the planes will be upright,
# aligned to the XY plane and will be 1 x 1
fileid.write('AttributeBegin\n')

fileid.write('\tTransformBegin\n')
fileid.write('\t\tTranslate 0 0 -0.5\n')
for n in range(numPlanes):
	fileid.write(zTranslate)
	fileid.write(shape)
fileid.write('\tTransformEnd\n')

## Uncomment the next block of code to generate
## PolyPlanes at right angles to the first group

#fileid.write('\tRotate 90 0 1 0\n')
#
#fileid.write('\tTransformBegin\n')
#fileid.write('\t\tTranslate 0 0 -0.5\n')
#for n in range(numPlanes):
#	fileid.write(zTranslate)
#	fileid.write(shape)
#fileid.write('\tTransformEnd\n')

 
fileid.write('AttributeEnd\n')
fileid.close()















