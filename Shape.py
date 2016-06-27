# -*- coding: utf-8 -*-
"""
Created on Wed Oct 28 14:09:55 2015

Shape should probably have been called outline but I have not yet bothered to
rename it. It is a subclass of LineGroup with extra methods for checking if it
is a closed polygon. The shape can be manifold (have internal holes) as long
as they are fully enclosed inside of the boundry.

@author: lvanhulle
"""
import Line as l
from LineGroup import LineGroup as LG
import constants as c
from functools import wraps
import numpy as np
import Point as p
from shapely.geometry.polygon import Polygon
from shapely.ops import cascaded_union
logger = c.logging.getLogger(__name__)
logger.setLevel(c.LOG_LEVEL)

def finishedOutline(func):
    """
    This method is used as a decorator to make sure that the Shape is valid
    before certian functions are used. See finishOutline() for what makes a 
    valid shape.
    """
    @wraps(func)
    def checker(self, *args):            
        if not self.outlineFinished:
            try:
                self.finishOutline()
            except Exception as e:
                try:
                    raise Exception('Shape must have a continuous closed outline to use '
                                + func.__name__ + '()\n\t\t' + e.message)
                except Exception as _:
                    raise e
        return func(self, *args)
    return checker

class Shape(LG):    
    def __init__(self, shape=None):
        LG.__init__(self, shape)
        self.outlineFinished = False

    def addCoordLoop(self, loop):
        loop_iter = iter(loop)
        pp = list(next(loop_iter))
        prev = p.Point(pp[:2]+[0])
        for curr in (p.Point(list(i[:2])+[0]) for i in loop_iter):
            if prev != curr:
                self.append(l.Line(prev,curr))
                prev = curr
        self.outlineFinished = False
    
    @finishedOutline
    def addInternalShape(self, inShape):
        if(not inShape.outlineFinished):
            print('********** Your internal shape was not a finished outline **********')
        if(not self.isInside(inShape.lines[0].start)):
            print('********** The internal shape is not inside the main shape. **********')
        if(self.doShapesIntersect(inShape)):
            print('********** Internal shape is not completely inside main shape. **********')
        
        for line in inShape:
            self.append(line)
    
    @finishedOutline
    def doShapesIntersect(self, inShape):
        for line in self.lines:
            for line2 in inShape.lines:
                result, point = line.segmentsIntersect(line2)
                if(result > 0):
                    return True
        return False
   
    def addLineGroup(self, inGroup):
        super(Shape, self).addLineGroup(inGroup)
        self.outlineFinished = False
    
    @finishedOutline    
    def subShape_gen(self):
        tempLines = []
        for line in self:
            tempLines.append(line)
            if tempLines[0].start == tempLines[-1].end:
                yield tempLines
                tempLines = []
        if len(tempLines) != 0:
            yield tempLines
            
    def closeShape(self):
        if(self[0].start != self[-1].end):
            self.append(l.Line(self[-1].end, self[0].start))
            
    
    def finishOutline(self):
        """
        Finishes the outline with a companion methods or throws an exception if it fails.
        
        Calls the companion method self.__finishOutline() and if that method
        does not throw an eror it assigns the returned value to self.lines and
        sets the outline as finsihed.
        """
        self.lines = self._finishOutline()
        self.outlineFinished = True

    def _finishOutline(self, normList=None, finishedShape=None):
        """ A companion method for finishOutline.
        
        The method sorts the lines so the the end of one line is touching
        the start of the next line and orients the lines so that the left side
        of the line is inside the shape. The shapes are allowed to have internal
        features but every feature must be continuous and closed.
        
        Parameters
        ----------
        normList - A NumPy array containing the normalVectors for every point in self
        finsihedShape - A list of Lines which will define the new shape
        
        Return
        ------
        finishedShape
        """
        if normList is None:
            normList = np.array([point.normalVector for point in self.iterPoints()], dtype=np.float)
        elif len(normList[(normList < np.inf)]) == 0:
            return
        if finishedShape is None:
            finishedShape = []

        """ Find the first index in normList that is not infinity. """
        firstLineIndex = np.where(normList[:,0] < np.inf)[0][0]//2
        
        """ firstLine is needed to know if the last line closes the shape. """
        firstLine = self[firstLineIndex]
        normList[firstLineIndex*2:firstLineIndex*2+2] = np.inf

        if not self.isInside(firstLine.getOffsetLine(c.EPSILON*2, c.INSIDE).getMidPoint()):
            """ Test if the inside (left) of the line is inside the part. If
            not flip the line. """
            firstLine = firstLine.fliped()
  
        testPoint = firstLine.end
        finishedShape.append(firstLine)
        while len(normList[(normList < np.inf)]) > 0:

            distances = np.linalg.norm(normList-testPoint.normalVector, None, 1)
            index = np.argmin(distances)
            nearestLine = self[index//2]
            
            if distances[index] > c.EPSILON:
                raise Exception('Shape has a gap of ' + str(distances[index]) +
                                ' at point ' + str(testPoint) + ', ' + 
                                str(p.Point(normList[index])))
            if index%2:
                """ If index is odd we are at the end of a line so the line needs to be flipped. """
                nearestLine = nearestLine.fliped()
            
            testPoint = nearestLine.end
            finishedShape.append(nearestLine)
            
            index //= 2
            """ Instead of deleting elements from the NumPy array we set the used
            vectors to infinity so they will not appear in the min. """
            normList[[index*2,index*2+1]] = np.inf
            
            if testPoint == firstLine.start:
                self._finishOutline(normList, finishedShape)
                return finishedShape
        dist = firstLine.start - finishedShape[-1].end
        if dist < c.EPSILON:
            return finishedShape
        raise Exception('Shape not closed. There is a gap of {:0.5f} at point {}'.format(dist, testPoint))

    @finishedOutline                                
    def offset(self, distance, desiredSide):
        """ Offsets a shape be distance to the desired side.
        
        The main offset method which calls _offset on each sub-shape of itself.
        If an error occurs while trying to offset a sub-shape the error is logged
        and the next shape is tried.
        
        Parameters
        ----------
        distance - The amount to offset
        desiredSide - either inside or outside
        
        Return
        ------
        newShape - The newly offset shape.
        
        """
        newShape = Shape()
        for subShape in self.subShape_gen():
            try:
                newShape.addLineGroup(self._offset(subShape, distance, desiredSide))
            except Exception as e:
                logger.info('One or more sub-shapes could not be offset. ' + str(e))
        return newShape
    
    def _offset(self, subShape, distance, desiredSide):
        """ A companion method for offset which actually does the offsetting.
        
        Each sub-shape of self is sent to this method. It currently works as follows:
        
        1) Runs through every line in the sub-shape, creating its offset, and
        trimming/joining the new lines as necessary.
        
        2) Tests every line against every other line to find intersections. If there
        are any intersections then the line is split at those points.
        
        3) Turns all of the split lines into a new Shape
        
        4) Checks all of the lines to see if their left side is still inside of the
        shape. If they are inside they are appended to a new list
        
        5) Turn the new list of lines into another Shape
        
        6) Finishes the new shape.
        
        Parameters
        ----------
        subShape - The sub-shape to be offset
        distance - The distance to offset
        desiredSide - The side (inside/outside) to offset
        
        Return
        ------
        offShape - The offset sub-shape.
        """
        points = []
        prevLine = subShape[-1].getOffsetLine(distance, desiredSide)
        for currLine in (line.getOffsetLine(distance, desiredSide)
                                for line in subShape):
            """ Offset all of the lines and trim/join their ends. """
            _, point = prevLine.segmentsIntersect(currLine, c.ALLOW_PROJECTION)
            if prevLine.calcT(point) > 0:
                """ Make sure the new point is ahead of the start of the prev line.
                If it is not we probably have two lines which have crossed the shape's
                medial axis and therefore their projected intersection is in a
                non-useful location.
                """
                points.append(point)
            else:
                points.append(prevLine.end)
                points.append(currLine.start)
            prevLine = currLine
            
        tempLines = [l.Line(p1, p2) for p1, p2 in self.pairwise_gen(points)]
        splitLines = []
        starts = np.array([line.start.get2DPoint() for line in tempLines])
        vectors = np.array([line.vector for line in tempLines])
        for iLine in tempLines:
            """ Find if the new lines cross eachother anywhere and if so split them. """
            pointSet = {iLine.start, iLine.end}
            Q_Less_P = iLine.start[:2] - starts
            denom = 1.0*np.cross(vectors, iLine.vector)
            all_t = np.cross(Q_Less_P, vectors)/denom
            all_u = np.cross(Q_Less_P, iLine.vector)/denom
            t = all_t[(0 <= all_u) & (all_u <= 1) & (0 <= all_t) & (all_t <= 1)]

            if len(t):
                pointSet |= set(p.Point(iLine.start.x + iLine.vector[c.X]*value,
                                        iLine.start.y+iLine.vector[c.Y]*value)
                                        for value in t)

            pointList = sorted(pointSet, key=iLine.calcT)

            splitLines.extend(l.Line(pointList[i], pointList[i+1])
                                for i in range(len(pointList)-1))

        tempShape = Shape(splitLines)
        shapeLines = []
        print('split Lines shape line 265')
        for line in splitLines:
            print(line)
            """ Check each line to see if its left side is inside the new offset shape. """
            if(tempShape.isInside(line.getOffsetLine(4*c.EPSILON, c.INSIDE).getMidPoint())):
                shapeLines.append(line)
#            else:
#                print('not added\n')

        offShape = Shape(shapeLines)
        offShape.finishOutline()
        return offShape
              
    def pairwise_gen(self, l1):
        """ A generator to turn a list into pairs so it can be made into lines.
        
        This is used to take a list of points and pair them so they can be made
        into lines. It pairs each item with its neighbors and even creates a pair
        of the last and first item.
        
        Parameter
        ---------
        l1 - an iterable
        
        Yields
        ------
        tuple of points
        """
        l1Iter = iter(l1)
        first = pre = next(l1Iter)
        for curr in l1Iter:
           yield pre, curr
           pre = curr
        yield pre, first            
    
    def trimJoin_Coro(self):
        """ Yields a list of lines that have their ends properly trimmed/joined
        after an offset.
        
        When the lines are offset their endpoints are just moved away the offset
        distance. If you offset a circle to the inside this would mean that
        all of the lines would overlap. If the circle was offset to the outside
        none of the lines would be touching. This function trims the overlapping
        ends and extends/joins the non touching ends.
        
        Yields
        ------
        in - Lines
        out - one big List of lines at the end.
        """
        offsetLines = []
        moveEnd = yield
        moveStart = yield
        while not(moveStart is None):
            _, point = moveEnd.segmentsIntersect(moveStart, c.ALLOW_PROJECTION)
            moveEnd = l.Line(moveEnd.start, point, moveEnd)
            moveStart = l.Line(point, moveStart.end, moveStart)
            offsetLines.append(moveEnd)
            moveEnd = moveStart
            moveStart = yield
        _, point = moveEnd.segmentsIntersect(offsetLines[0], c.ALLOW_PROJECTION)
        moveEnd = l.Line(moveEnd.start, point, moveEnd)
        offsetLines.append(moveEnd)
        offsetLines[0] = l.Line(point, offsetLines[0].end, offsetLines[0])
        yield offsetLines

    def isInside(self, point, ray=np.array([0.998, 0.067])):
        """
        This method determines if the point is inside
        or outside the shape. Returns the side of the shape the point is on.
        
        If a line is drawn from the point to outside of the shape the number
        of times that line intersects with the shape determines if the point was inside
        or outside. If the number of intersections is even then the point was outside
        of the shape. If the number of intersections is odd then the point is inside.
        
        Problems arise if the line passes through the endpoints of two lines so
        if that happens draw a new line and test again. This redraw is handled
        through recursion.
        
        The default ray is at an angle of about 3.6 degrees. A little testing
        showed this angle to be fairly unlikely to cause endpoint collisions.
        When a collision does occur we draw the new ray at the current angle plus
        90 degrees plus a random value between [0-1). The 90 degrees is to make
        the new ray perpendicular to the current one and hopefully less likely
        to hit another point. The random amount is to avoid hitting another endpoint
        which are usually at a regular interval.
        """
#        print('New isInside test')
#        print('Point: ', point)
        if(point[c.X] > self.maxX or point[c.X] < self.minX): return c.OUTSIDE
        if(point[c.Y] > self.maxY or point[c.Y] < self.minY): return c.OUTSIDE

        Q_Less_P = point[:2] - self.starts
        denom = 1.0*np.cross(self.vectors, ray)
        all_u = np.cross(Q_Less_P, self.vectors)/denom # the intersection ratio on ray
        all_t = np.cross(Q_Less_P, ray)/denom # The intersection ratio on self.lines 

#        print('all_u')
#        print(all_u)
#        print('all_t')
#        print(all_t)
        all_t = all_t[all_u > 0]

        endPoints = (np.abs(all_t) < c.EPSILON) | (np.abs(1-all_t) < c.EPSILON)
        if np.any(endPoints):
#            time.sleep(0.5)
            oldAngle = np.arctan2(*ray[::-1])
            newAngle = oldAngle+(90+np.random.rand())/360.0*2*np.pi
            logger.info('Recursion made in isInside()\n\tcollision at angle: ' +
                            '{:0.1f} \n\tnext angle attempt: {:0.1f} \
                            \n\tPoint: {}'.format(
                            oldAngle*360/2.0/np.pi, newAngle*360/2/np.pi, point))
            newRay=np.array([np.cos(newAngle), np.sin(newAngle)])
            return  self.isInside(point, newRay)
            
        intersections = (0 < all_t) & (all_t < 1)
#        print('Intersections: ', intersections)
        return (c.INSIDE if np.sum(intersections) % 2 else c.OUTSIDE)

class _SidedPolygon:
    def __init__(self, poly, level):
        self.poly = poly
        self.level = level
        self.isFeature = not level%2
    def contains(self, other):
        return self.poly.contains(other)

    def offset(self, dist, side):
        if dist == 0:
            return _SidedPolygon(self.poly, self.level)
        if dist < 0:
            side = not side
            dist = abs(dist)
        if (side == c.OUTSIDE and self.isFeature) or (side == c.INSIDE and not self.isFeature):
            return _SidedPolygon(self.poly.buffer(dist), self.level)
        try:
            buffPoly = self.poly.exterior.buffer(dist)
            if len(buffPoly.interiors) > 1:
                inPoly = cascaded_union([Polygon(i) for i in buffPoly.interiors])            
            else:
                inPoly = Polygon(buffPoly.interiors[0])
            return _SidedPolygon(inPoly, self.level)
        except Exception:
            return None
    
    def brim(self, dist):
        return self.offset(dist, c.OUTSIDE)
    
    def shell(self, dist):
        return self.offset(dist, c.INSIDE)

class Section:
    def __init__(self, section):
        self.section = section
        self.sidedPolygons = self.createSided([Polygon(i) for i in section.discrete])
        
    @property
    def shape(self):
        shape = Shape()
        for sidedPolygon in self.sidedPolygons:
            for coords in self.polygonCoords(sidedPolygon.poly):
                shape.addCoordLoop(coords)        
    
    def re_union(self, polies):
        final = None
        for ps in polies:
            if final is None:
                if ps.isFeature:
                    final = ps.poly
            elif ps.isFeature:
                final = final.union(ps.poly)
            else:
                final = final.difference(ps.poly)
        return final    

    def offset(self, dist, side):
        union = self.re_union(filter(None, (j.offset(dist, side) for j in self.sidedPolygons)))
        if not union:
            return None
        shape = Shape()
        try:
            for coords in self.polygonCoords(union):
                shape.addCoordLoop(coords)
        except Exception:
            for polygon in union:
                for coords in self.polygonCoords(polygon):
                    shape.addCoordLoop(coords)
        return shape
        
    def polygonCoords(self, polygon):
        yield polygon.exterior.coords
        for inner in polygon.interiors:
            yield inner.coords
        
    def createSided(self, polys):
        sidedPolygons = []
        polys = sorted(polys, key = lambda x: x.area, reverse=True)
        def io(thisPoly, index=0):
            while index < len(polys):
                if thisPoly.contains(polys[index]):
                    new = _SidedPolygon(polys[index], thisPoly.level+1)
                    sidedPolygons.append(new)
                    polys.pop(index)
                    io(new, index)
                else:
                    index += 1
        while polys:
            first = _SidedPolygon(polys.pop(0), 0)
            sidedPolygons.append(first)
            io(first)
        return sidedPolygons    
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        