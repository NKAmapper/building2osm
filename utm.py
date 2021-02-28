'''
This module converts between lat long and UTM coordinates.
 
Geographic coordinates are entered and displayed in degrees.
Negative numbers indicate West longitudes and South latitudes.
UTM coordinates are entered and displayed in meters.
The ellipsoid model used for computations is WGS84.
 
Usage:
import latlonutm as ll
[[northing, easting], zone, hemi] = ll.LatLonToUtm(lat, lon)
[lat, lon] = ll.UtmToLatLon(northing, easting, zone, southhemi)

Copied from: nenadsprojects
https://nenadsprojects.wordpress.com/2012/12/27/latitude-and-longitude-utm-conversion/

Converted from javascript by Nenad Uzunovic
Original source
http://home.hiwaay.net/~taylorc/toolbox/geography/geoutm.html
'''
 
import math


# Ellipsoid model constants (actual values here are for WGS84)
sm_a = 6378137.0
sm_b = 6356752.314
sm_EccSquared = 6.69437999013e-03
 
UTMScaleFactor = 0.9996


def DegToFloat(degrees, minutes, seconds):
    '''
    Converts angle in format deg,min,sec to a floating point number
    '''
    if (degrees>=0):
        return (degrees) + (minutes/60.0) + (seconds/3600.0)
    else:
        return (degrees) - (minutes/60.0) - (seconds/3600.0)


def DegToRad(deg):
    '''
    Converts degrees to radians.
    '''
    return (deg / 180.0 * math.pi)


def RadToDeg(rad):
    '''
    Converts radians to degrees.
    '''
    return (rad / math.pi * 180.0)


def ArcLengthOfMeridian(phi):
    '''
    Computes the ellipsoidal distance from the equator to a point at a
    given latitude.
 
    Reference: Hoffmann-Wellenhof, B., Lichtenegger, H., and Collins, J.,
    GPS: Theory and Practice, 3rd ed.  New York: Springer-Verlag Wien, 1994.
 
    Inputs:
    phi - Latitude of the point, in radians.
 
    Globals:
    sm_a - Ellipsoid model major axis.
    sm_b - Ellipsoid model minor axis.
 
    Outputs:
    The ellipsoidal distance of the point from the equator, in meters.
    '''
 
    # Precalculate n
    n = (sm_a - sm_b) / (sm_a + sm_b)
 
    # Precalculate alpha
    alpha = ((sm_a + sm_b) / 2.0) \
        * (1.0 + (math.pow (n, 2.0) / 4.0) + (math.pow (n, 4.0) / 64.0))
 
    # Precalculate beta
    beta = (-3.0 * n / 2.0) + (9.0 * math.pow (n, 3.0) / 16.0) \
        + (-3.0 * math.pow (n, 5.0) / 32.0)
 
    # Precalculate gamma
    gamma = (15.0 * math.pow (n, 2.0) / 16.0) \
        + (-15.0 * math.pow (n, 4.0) / 32.0)
 
    # Precalculate delta
    delta = (-35.0 * math.pow (n, 3.0) / 48.0) \
        + (105.0 * math.pow (n, 5.0) / 256.0)
 
    # Precalculate epsilon
    epsilon = (315.0 * math.pow (n, 4.0) / 512.0)
 
    # Now calculate the sum of the series and return
    result = alpha \
        * (phi + (beta * math.sin (2.0 * phi)) \
           + (gamma * math.sin (4.0 * phi)) \
           + (delta * math.sin (6.0 * phi)) \
           + (epsilon * math.sin (8.0 * phi)))
 
    return result


def UTMCentralMeridian(zone):
    '''
    Determines the central meridian for the given UTM zone.
 
    Inputs:
    zone - An integer value designating the UTM zone, range [1,60].
 
    Outputs:
    The central meridian for the given UTM zone, in radians, or zero
    if the UTM zone parameter is outside the range [1,60].
    Range of the central meridian is the radian equivalent of [-177,+177].
    '''
    return DegToRad(-183.0 + (zone * 6.0))


def FootpointLatitude(y):
    '''
    Computes the footpoint latitude for use in converting transverse
    Mercator coordinates to ellipsoidal coordinates.
 
    Reference: Hoffmann-Wellenhof, B., Lichtenegger, H., and Collins, J.,
    GPS: Theory and Practice, 3rd ed.  New York: Springer-Verlag Wien, 1994.
 
    Inputs:
    y - The UTM northing coordinate, in meters.
 
    Outputs:
    The footpoint latitude, in radians.
    '''
 
    # Precalculate n (Eq. 10.18)
    n = (sm_a - sm_b) / (sm_a + sm_b)
 
    # Precalculate alpha_ (Eq. 10.22)
    # (Same as alpha in Eq. 10.17)
    alpha_ = ((sm_a + sm_b) / 2.0) \
        * (1 + (math.pow (n, 2.0) / 4) + (math.pow (n, 4.0) / 64))
 
    # Precalculate y_ (Eq. 10.23)
    y_ = y / alpha_
 
    # Precalculate beta_ (Eq. 10.22)
    beta_ = (3.0 * n / 2.0) + (-27.0 * math.pow (n, 3.0) / 32.0) \
        + (269.0 * math.pow (n, 5.0) / 512.0)
 
    # Precalculate gamma_ (Eq. 10.22)
    gamma_ = (21.0 * math.pow (n, 2.0) / 16.0) \
        + (-55.0 * math.pow (n, 4.0) / 32.0)
 
    # Precalculate delta_ (Eq. 10.22)
    delta_ = (151.0 * math.pow (n, 3.0) / 96.0) \
        + (-417.0 * math.pow (n, 5.0) / 128.0)
 
    # Precalculate epsilon_ (Eq. 10.22)
    epsilon_ = (1097.0 * math.pow (n, 4.0) / 512.0)
 
    # Now calculate the sum of the series (Eq. 10.21)
    result = y_ + (beta_ * math.sin (2.0 * y_)) \
        + (gamma_ * math.sin (4.0 * y_)) \
        + (delta_ * math.sin (6.0 * y_)) \
        + (epsilon_ * math.sin (8.0 * y_))
 
    return result


def MapLatLonToXY(phi, lambda_pt, lambda_ctr):
    '''
    Converts a latitude/longitude pair to x and y coordinates in the
    Transverse Mercator projection.  Note that Transverse Mercator is not
    the same as UTM; a scale factor is required to convert between them.
 
    Reference: Hoffmann-Wellenhof, B., Lichtenegger, H., and Collins, J.,
    GPS: Theory and Practice, 3rd ed.  New York: Springer-Verlag Wien, 1994.
 
    Inputs:
    phi - Latitude of the point, in radians.
    lambda_pt - Longitude of the point, in radians.
    lambda_ctr - Longitude of the central meridian to be used, in radians.
 
    Outputs:
    xy - A 2-element array containing the x and y coordinates
    of the computed point.
    '''
 
    # Precalculate ep2
    ep2 = (math.pow (sm_a, 2.0) - math.pow (sm_b, 2.0)) / math.pow (sm_b, 2.0)
 
    # Precalculate nu2
    nu2 = ep2 * math.pow (math.cos (phi), 2.0)
 
    # Precalculate N
    N = math.pow (sm_a, 2.0) / (sm_b * math.sqrt (1 + nu2))
 
    # Precalculate t
    t = math.tan (phi)
    t2 = t * t
    # tmp = (t2 * t2 * t2) - math.pow (t, 6.0)
 
    # Precalculate l
    l = lambda_pt - lambda_ctr
 
    # Precalculate coefficients for l**n in the equations below
    #   so a normal human being can read the expressions for easting
    #   and northing
    #   -- l**1 and l**2 have coefficients of 1.0
    l3coef = 1.0 - t2 + nu2
 
    l4coef = 5.0 - t2 + 9 * nu2 + 4.0 * (nu2 * nu2)
 
    l5coef = 5.0 - 18.0 * t2 + (t2 * t2) + 14.0 * nu2 \
        - 58.0 * t2 * nu2
 
    l6coef = 61.0 - 58.0 * t2 + (t2 * t2) + 270.0 * nu2 \
        - 330.0 * t2 * nu2
 
    l7coef = 61.0 - 479.0 * t2 + 179.0 * (t2 * t2) - (t2 * t2 * t2)
 
    l8coef = 1385.0 - 3111.0 * t2 + 543.0 * (t2 * t2) - (t2 * t2 * t2)
 
    # Calculate easting (x)
    xy = [0.0, 0.0]
    xy[0] = N * math.cos (phi) * l \
        + (N / 6.0 * math.pow (math.cos (phi), 3.0) * l3coef * math.pow (l, 3.0)) \
        + (N / 120.0 * math.pow (math.cos (phi), 5.0) * l5coef * math.pow (l, 5.0)) \
        + (N / 5040.0 * math.pow (math.cos (phi), 7.0) * l7coef * math.pow (l, 7.0))
 
    # Calculate northing (y)
    xy[1] = ArcLengthOfMeridian (phi) \
        + (t / 2.0 * N * math.pow (math.cos (phi), 2.0) * math.pow (l, 2.0)) \
        + (t / 24.0 * N * math.pow (math.cos (phi), 4.0) * l4coef * math.pow (l, 4.0)) \
        + (t / 720.0 * N * math.pow (math.cos (phi), 6.0) * l6coef * math.pow (l, 6.0)) \
        + (t / 40320.0 * N * math.pow (math.cos (phi), 8.0) * l8coef * math.pow (l, 8.0))
 
    return xy


def MapXYToLatLon(x, y, lambda_ctr):
    '''
    Converts x and y coordinates in the Transverse Mercator projection to
    a latitude/longitude pair.  Note that Transverse Mercator is not
    the same as UTM; a scale factor is required to convert between them.
 
    Reference: Hoffmann-Wellenhof, B., Lichtenegger, H., and Collins, J.,
    GPS: Theory and Practice, 3rd ed.  New York: Springer-Verlag Wien, 1994.
 
    Inputs:
    x - The easting of the point, in meters.
    y - The northing of the point, in meters.
    lambda_ctr - Longitude of the central meridian to be used, in radians.
 
    Outputs:
    philambda - A 2-element containing the latitude and longitude
    in radians.
 
    Remarks:
    The local variables Nf, nuf2, tf, and tf2 serve the same purpose as
    N, nu2, t, and t2 in MapLatLonToXY, but they are computed with respect
    to the footpoint latitude phif.
 
    x1frac, x2frac, x2poly, x3poly, etc. are to enhance readability and
    to optimize computations.
    '''
 
    # Get the value of phif, the footpoint latitude.
    phif = FootpointLatitude (y)
 
    # Precalculate ep2
    ep2 = (math.pow (sm_a, 2.0) - math.pow (sm_b, 2.0)) \
        / math.pow (sm_b, 2.0)
 
    # Precalculate cos (phif)
    cf = math.cos (phif)
 
    # Precalculate nuf2
    nuf2 = ep2 * math.pow (cf, 2.0)
 
    # Precalculate Nf and initialize Nfpow
    Nf = math.pow (sm_a, 2.0) / (sm_b * math.sqrt (1 + nuf2))
    Nfpow = Nf
 
    # Precalculate tf
    tf = math.tan (phif)
    tf2 = tf * tf
    tf4 = tf2 * tf2
 
    # Precalculate fractional coefficients for x**n in the equations
    #   below to simplify the expressions for latitude and longitude.
    x1frac = 1.0 / (Nfpow * cf)
 
    Nfpow *= Nf   # now equals Nf**2)
    x2frac = tf / (2.0 * Nfpow)
 
    Nfpow *= Nf   # now equals Nf**3)
    x3frac = 1.0 / (6.0 * Nfpow * cf)
 
    Nfpow *= Nf   # now equals Nf**4)
    x4frac = tf / (24.0 * Nfpow)
 
    Nfpow *= Nf   # now equals Nf**5)
    x5frac = 1.0 / (120.0 * Nfpow * cf)
 
    Nfpow *= Nf   # now equals Nf**6)
    x6frac = tf / (720.0 * Nfpow)
 
    Nfpow *= Nf   # now equals Nf**7)
    x7frac = 1.0 / (5040.0 * Nfpow * cf)
 
    Nfpow *= Nf   # now equals Nf**8)
    x8frac = tf / (40320.0 * Nfpow)
 
    # Precalculate polynomial coefficients for x**n.
    #   -- x**1 does not have a polynomial coefficient.
    x2poly = -1.0 - nuf2
 
    x3poly = -1.0 - 2 * tf2 - nuf2
 
    x4poly = 5.0 + 3.0 * tf2 + 6.0 * nuf2 - 6.0 * tf2 * nuf2 \
        - 3.0 * (nuf2 *nuf2) - 9.0 * tf2 * (nuf2 * nuf2)
 
    x5poly = 5.0 + 28.0 * tf2 + 24.0 * tf4 + 6.0 * nuf2 + 8.0 * tf2 * nuf2
 
    x6poly = -61.0 - 90.0 * tf2 - 45.0 * tf4 - 107.0 * nuf2 \
        + 162.0 * tf2 * nuf2
 
    x7poly = -61.0 - 662.0 * tf2 - 1320.0 * tf4 - 720.0 * (tf4 * tf2)
 
    x8poly = 1385.0 + 3633.0 * tf2 + 4095.0 * tf4 + 1575 * (tf4 * tf2)
 
    # Calculate latitude
    philambda = [0.0, 0.0]
    philambda[0] = phif + x2frac * x2poly * (x * x) \
        + x4frac * x4poly * math.pow (x, 4.0) \
        + x6frac * x6poly * math.pow (x, 6.0) \
        + x8frac * x8poly * math.pow (x, 8.0)
 
    # Calculate longitude
    philambda[1] = lambda_ctr + x1frac * x \
        + x3frac * x3poly * math.pow (x, 3.0) \
        + x5frac * x5poly * math.pow (x, 5.0) \
        + x7frac * x7poly * math.pow (x, 7.0)
 
    return philambda


def LatLonToUTMXY(lat, lon, zone):
    '''
    Converts a latitude/longitude pair to x and y coordinates in the
    Universal Transverse Mercator projection.
 
    Inputs:
    lat - Latitude of the point, in radians.
    lon - Longitude of the point, in radians.
    zone - UTM zone to be used for calculating values for x and y.
    If zone is less than 1 or greater than 60, the routine
    will determine the appropriate zone from the value of lon.
 
    Outputs:
    xy - A 2-element array where the UTM x and y values will be stored.
    '''
 
    xy = MapLatLonToXY(lat, lon, UTMCentralMeridian(zone))
 
    # Adjust easting and northing for UTM system.
    xy[0] = xy[0] * UTMScaleFactor + 500000.0
    xy[1] = xy[1] * UTMScaleFactor
    if (xy[1] < 0.0):
        xy[1] = xy[1] + 10000000.0
 
    return xy


def UTMXYToLatLon(x, y, zone, southhemi):
    '''
    Converts x and y coordinates in the Universal Transverse Mercator
    projection to a latitude/longitude pair.
 
    Inputs:
    x - The easting of the point, in meters.
    y - The northing of the point, in meters.
    zone - The UTM zone in which the point lies.
    southhemi - True if the point is in the southern hemisphere;
    false otherwise.
 
    Outputs:
    latlon - A 2-element array containing the latitude and
    longitude of the point, in radians.
    '''
    x -= 500000.0
    x /= UTMScaleFactor
 
    # If in southern hemisphere, adjust y accordingly.
    if (southhemi):
        y -= 10000000.0
 
    y /= UTMScaleFactor
 
    cmeridian = UTMCentralMeridian(zone)
    latlon = MapXYToLatLon(x, y, cmeridian)
 
    return latlon


def LatLonToUtm(lat, lon):
    '''
    Converts lat lon to utm
 
    Inputs:
    lat - lattitude in degrees
    lon - longitude in degrees
 
    Outputs:
    xy - utm x(easting), y(northing)
    zone - utm zone
    hemi - 'N' or 'S'
    '''
 
    if ((lon < -180.0) or (180.0 <= lon)):
        print ('The longitude you entered is out of range -', lon)
        print ('Please enter a number in the range [-180, 180).')
        return 0
 
    if ((lat < -90.0) or (90.0 < lat)):
        print ('The latitude you entered is out of range -', lat)
        print ('Please enter a number in the range [-90, 90].')
 
    # Compute the UTM zone.
    zone = math.floor ((lon + 180.0) / 6) + 1
 
    # Convert
    xy = LatLonToUTMXY (DegToRad(lat), DegToRad(lon), zone)
 
    # Determine hemisphere
    hemi = 'N'
    if (lat < 0):
        hemi = 'S'
 
    return [xy, zone, hemi]


def UtmToLatLon(x, y, zone, hemi):
    '''
    Converts UTM coordinates to lat long
 
    Inputs:
    x - easting (in meters)
    y - northing (in meters)
    zone - UTM zone
    hemi - 'N' or 'S'
 
    Outputs:
    latlong - [lattitude, longitude] (in degrees)
    '''
    if ((zone < 1) or (60 < zone)):
        print ('The UTM zone you entered is out of range -', zone)
        print ('Please enter a number in the range [1, 60].')
        return 0
 
    if ((hemi != 'N') and (hemi != 'S')):
        print ('The hemisphere you entered is wrong -', hemi)
        print ('Please enter N or S')
 
    southhemi = False
    if (hemi == 'S'):
        southhemi = True
 
    # Convert
    latlon = UTMXYToLatLon(x, y, zone, southhemi)
 
    # Convert to degrees
    latlon[0] = RadToDeg(latlon[0])
    latlon[1] = RadToDeg(latlon[1])
 
    return latlon